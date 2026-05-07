from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import torch
from torch import Tensor, nn


NEG_INF = -1e9


def masked_mean(values: Tensor, mask: Tensor, dim: int) -> Tensor:
    weights = mask.to(values.dtype)
    denom = weights.sum(dim=dim, keepdim=True).clamp_min(1.0)
    return (values * weights).sum(dim=dim) / denom.squeeze(dim)


@dataclass
class PointerDecoderOutput:
    logits: Tensor
    predictions: List[List[int]]


class PointerNetworkCutSelector(nn.Module):
    def __init__(
        self,
        vocab_size: int,
        numeric_feature_dim: int,
        token_embed_dim: int = 128,
        edge_hidden_dim: int = 256,
        encoder_layers: int = 1,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        self.vocab_size = vocab_size
        self.numeric_feature_dim = numeric_feature_dim
        self.token_embed_dim = token_embed_dim
        self.edge_hidden_dim = edge_hidden_dim
        self.encoder_layers = encoder_layers
        self.dropout_rate = dropout

        self.token_embedding = nn.Embedding(vocab_size, token_embed_dim, padding_idx=0)
        self.numeric_projection = nn.Sequential(
            nn.Linear(numeric_feature_dim, token_embed_dim),
            nn.ReLU(),
            nn.Linear(token_embed_dim, token_embed_dim),
        )
        self.edge_projection = nn.Sequential(
            nn.Linear(token_embed_dim * 2, edge_hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
        )
        self.encoder = nn.LSTM(
            input_size=edge_hidden_dim,
            hidden_size=edge_hidden_dim // 2,
            num_layers=encoder_layers,
            batch_first=True,
            bidirectional=True,
            dropout=dropout if encoder_layers > 1 else 0.0,
        )
        self.decoder_cell = nn.LSTMCell(edge_hidden_dim, edge_hidden_dim)
        self.decoder_init_h = nn.Linear(edge_hidden_dim, edge_hidden_dim)
        self.decoder_init_c = nn.Linear(edge_hidden_dim, edge_hidden_dim)
        self.pointer_query = nn.Linear(edge_hidden_dim, edge_hidden_dim, bias=False)
        self.pointer_key = nn.Linear(edge_hidden_dim, edge_hidden_dim, bias=False)
        self.pointer_v = nn.Linear(edge_hidden_dim, 1, bias=False)
        self.eos_head = nn.Sequential(
            nn.Linear(edge_hidden_dim, edge_hidden_dim),
            nn.Tanh(),
            nn.Linear(edge_hidden_dim, 1),
        )
        self.start_input = nn.Parameter(torch.zeros(edge_hidden_dim))
        self.dropout = nn.Dropout(dropout)

    def encode_edges(self, edge_token_ids: Tensor, edge_token_mask: Tensor, numeric_features: Tensor) -> Tensor:
        token_emb = self.token_embedding(edge_token_ids)
        token_mask = edge_token_mask.unsqueeze(-1)
        text_repr = masked_mean(token_emb, token_mask, dim=2)
        numeric_repr = self.numeric_projection(numeric_features)
        edge_inputs = torch.cat([text_repr, numeric_repr], dim=-1)
        edge_inputs = self.edge_projection(edge_inputs)
        encodings, _ = self.encoder(edge_inputs)
        return self.dropout(encodings)

    def _pointer_logits(self, decoder_hidden: Tensor, edge_encodings: Tensor) -> Tensor:
        query = self.pointer_query(decoder_hidden).unsqueeze(1)
        keys = self.pointer_key(edge_encodings)
        scores = self.pointer_v(torch.tanh(query + keys)).squeeze(-1)
        return scores

    def _attention_context(self, edge_logits: Tensor, edge_encodings: Tensor, available_mask: Tensor) -> Tensor:
        masked_logits = edge_logits.masked_fill(~available_mask, NEG_INF)
        weights = torch.softmax(masked_logits, dim=-1)
        weights = weights * available_mask.to(weights.dtype)
        weights = weights / weights.sum(dim=-1, keepdim=True).clamp_min(1e-8)
        return torch.bmm(weights.unsqueeze(1), edge_encodings).squeeze(1)

    def forward(
        self,
        edge_token_ids: Tensor,
        edge_token_mask: Tensor,
        numeric_features: Tensor,
        edge_mask: Tensor,
        target_positions: Optional[Tensor] = None,
        max_decode_steps: Optional[int] = None,
    ) -> PointerDecoderOutput:
        batch_size, max_edges, _ = edge_token_ids.shape
        device = edge_token_ids.device
        eos_index = max_edges
        edge_encodings = self.encode_edges(edge_token_ids, edge_token_mask, numeric_features)
        pooled = masked_mean(edge_encodings, edge_mask.unsqueeze(-1), dim=1)
        hidden = torch.tanh(self.decoder_init_h(pooled))
        cell = torch.tanh(self.decoder_init_c(pooled))
        decoder_input = self.start_input.unsqueeze(0).expand(batch_size, -1)
        available_mask = edge_mask.clone()
        finished = torch.zeros(batch_size, dtype=torch.bool, device=device)
        logits_per_step: List[Tensor] = []
        predictions: List[List[int]] = [[] for _ in range(batch_size)]
        total_steps = max_decode_steps or (target_positions.size(1) if target_positions is not None else max_edges + 1)

        for step in range(total_steps):
            hidden, cell = self.decoder_cell(decoder_input, (hidden, cell))
            raw_edge_logits = self._pointer_logits(hidden, edge_encodings)
            masked_edge_logits = raw_edge_logits.masked_fill(~available_mask, NEG_INF)
            eos_logits = self.eos_head(hidden).squeeze(-1)
            step_logits = torch.cat([masked_edge_logits, eos_logits.unsqueeze(-1)], dim=-1)
            logits_per_step.append(step_logits)

            decoder_input = self._attention_context(raw_edge_logits, edge_encodings, available_mask)

            if target_positions is not None:
                chosen = target_positions[:, step].clone()
                chosen = torch.where(chosen < 0, torch.full_like(chosen, eos_index), chosen)
            else:
                chosen = step_logits.argmax(dim=-1)

            for batch_idx, next_idx in enumerate(chosen.tolist()):
                if finished[batch_idx]:
                    continue
                if next_idx == eos_index:
                    finished[batch_idx] = True
                    continue
                predictions[batch_idx].append(next_idx)
                available_mask[batch_idx, next_idx] = False

            if finished.all():
                break

        logits = torch.stack(logits_per_step, dim=1)
        return PointerDecoderOutput(logits=logits, predictions=predictions)

    @torch.no_grad()
    def predict(
        self,
        edge_token_ids: Tensor,
        edge_token_mask: Tensor,
        numeric_features: Tensor,
        edge_mask: Tensor,
        max_decode_steps: Optional[int] = None,
    ) -> List[List[int]]:
        output = self.forward(
            edge_token_ids=edge_token_ids,
            edge_token_mask=edge_token_mask,
            numeric_features=numeric_features,
            edge_mask=edge_mask,
            target_positions=None,
            max_decode_steps=max_decode_steps,
        )
        return output.predictions

    def get_config(self) -> Dict[str, int | float]:
        return {
            "vocab_size": self.vocab_size,
            "numeric_feature_dim": self.numeric_feature_dim,
            "token_embed_dim": self.token_embed_dim,
            "edge_hidden_dim": self.edge_hidden_dim,
            "encoder_layers": self.encoder_layers,
            "dropout": self.dropout_rate,
        }
