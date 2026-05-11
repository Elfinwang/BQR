from sqlglot import parse_one, exp
from syntax_tree import build_syntax_tree, find_subqueries, extract_and_fix_subqueries
from collections import OrderedDict
import re
import random
import json
from config import DB_CONFIG

# 预加载所有字段名
def load_all_tpch_columns(json_path):
    with open(json_path, "r") as f:
        schema = json.load(f)
    all_columns = set()
    for table in schema:
        for col in table["columns"]:
            all_columns.add(col["name"])
    return all_columns


DSB_STRING_COLUMNS = {
       "call_center": {
        "cc_state", "cc_mkt_class", "cc_mkt_desc", "cc_market_manager", "cc_zip", 
        "cc_division_name", "cc_country", "cc_company_name", "cc_call_center_id", 
        "cc_street_number", "cc_street_name", "cc_street_type", "cc_suite_number", 
        "cc_name", "cc_class", "cc_city", "cc_county", "cc_hours", "cc_manager"
    },
    "catalog_page": {
        "cp_type", "cp_catalog_page_id", "cp_department", "cp_description"
    },
    "customer": {
        "c_customer_id", "c_last_name", "c_preferred_cust_flag", "c_birth_country", 
        "c_login", "c_email_address", "c_salutation", "c_first_name"
    },
    "customer_address": {
        "ca_street_number", "ca_street_name", "ca_street_type", "ca_suite_number", 
        "ca_city", "ca_county", "ca_state", "ca_zip", "ca_country", "ca_location_type", 
        "ca_address_id"
    },
    "customer_demographics": {
        "cd_gender", "cd_marital_status", "cd_education_status", "cd_credit_rating"
    },
    "date_dim": {
        "d_current_year", "d_date_id", "d_day_name", "d_quarter_name", "d_holiday", 
        "d_weekend", "d_following_holiday", "d_current_day", "d_current_week", 
        "d_current_month", "d_current_quarter"
    },
    "dbgen_version": {
        "dv_version", "dv_cmdline_args"
    },
    "household_demographics": {
        "hd_buy_potential"
    },
    "item": {
        "i_class", "i_container", "i_category", "i_item_id", "i_product_name", 
        "i_manufact", "i_item_desc", "i_size", "i_formulation", "i_color", 
        "i_brand", "i_units"
    },
    "promotion": {
        "p_channel_tv", "p_channel_radio", "p_channel_press", "p_channel_event", 
        "p_channel_demo", "p_channel_details", "p_purpose", "p_discount_active", 
        "p_promo_id", "p_promo_name", "p_channel_dmail", "p_channel_email", 
        "p_channel_catalog"
    },
    "reason": {
        "r_reason_id", "r_reason_desc"
    },
    "ship_mode": {
        "sm_ship_mode_id", "sm_type", "sm_code", "sm_carrier", "sm_contract"
    },
    "store": {
        "s_geography_class", "s_market_desc", "s_market_manager", "s_zip", 
        "s_division_name", "s_country", "s_company_name", "s_street_number", 
        "s_store_id", "s_street_name", "s_street_type", "s_suite_number", 
        "s_store_name", "s_city", "s_county", "s_hours", "s_manager", "s_state"
    },
    "time_dim": {
        "t_meal_time", "t_time_id", "t_am_pm", "t_shift", "t_sub_shift"
    },
    "warehouse": {
        "w_country", "w_street_number", "w_street_name", "w_street_type", 
        "w_suite_number", "w_city", "w_county", "w_state", "w_zip", 
        "w_warehouse_id", "w_warehouse_name"
    },
    "web_page": {
        "wp_web_page_id", "wp_url", "wp_autogen_flag", "wp_type"
    },
    "web_site": {
        "web_zip", "web_mkt_class", "web_mkt_desc", "web_market_manager", 
        "web_country", "web_company_name", "web_street_number", "web_street_name", 
        "web_street_type", "web_site_id", "web_suite_number", "web_city", 
        "web_name", "web_county", "web_state", "web_class", "web_manager"
    }

}

TPCH_STRING_COLUMNS = {
    "customer": {"c_name", "c_address", "c_phone", "c_mktsegment", "c_comment"},
    "lineitem": {"l_returnflag", "l_linestatus", "l_shipinstruct", "l_shipmode", "l_comment"},
    "nation": {"n_name", "n_comment"},
    "orders": {"o_orderstatus", "o_orderpriority", "o_clerk", "o_comment"},
    "part": {"p_name", "p_mfgr", "p_brand", "p_type", "p_container", "p_comment"},
    "partsupp": {"ps_comment"},
    "region": {"r_name", "r_comment"},
    "supplier": {"s_name", "s_address", "s_phone", "s_comment"}

}



BIRD_SQL_COLUMNS = {

    # bird-sql (card_games) 数据库的字符串字段
    "card_choice": {"non_valid_cards"},
    "card_type": {"type"},
    "cards": {
        "artist", "asciiname", "availability", "bordercolor", "cardkingdomfoilid", "cardkingdomid",
        "coloridentity", "colorindicator", "colors", "dueldeck", "facename", "flavorname", "flavortext",
        "frameeffects", "frameversion", "hand", "keywords", "layout", "leadershipskills", "life", "loyalty",
        "manacost", "mcmid", "mcmmetaid", "mtgarenaid", "mtgjsonv4id", "mtgofoilid", "mtgoid", "multiverseid",
        "name", "number", "originalreleasedate", "originaltext", "originaltype", "otherfaceids", "power",
        "printings", "promotypes", "purchaseurls", "rarity", "scryfallid", "scryfallillustrationid",
        "scryfalloracleid", "setcode", "side", "subtypes", "supertypes", "tcgplayerproductid", "text",
        "toughness", "type", "types", "uuid", "variations", "watermark"
    },
    "cards_info": {"name"},
    "contents": {
        "item", "size", "condition", "notes", "serial_number", "custom_properties", "item_sku",
        "origin_country", "last_checked_by"
    },
    "foreign_data": {"flavortext", "language", "name", "text", "type", "uuid"},
    "info": {"info"},
    "legalities": {"format", "status", "uuid"},
    "packages": {
        "name", "description", "status", "metadata", "tracking_id", "last_scanned_location",
        "internal_notes"
    },
    "rulings": {"text", "uuid"},
    "set_translations": {"language", "setcode", "translation"},
    "sets": {
        "block", "booster", "code", "keyrunecode", "mcmname", "mtgocode", "name", "parentcode",
        "type"
    },
     "circuits": {"circuitref", "name", "location", "country", "url"},
    "constructorresults": {"status"},
    "constructors": {"constructorref", "name", "nationality", "url"},
    "constructorstandings": {"positiontext"},
    "drivers": {"driverref", "code", "forename", "surname", "nationality", "url"},
    "driverstandings": {"positiontext"},
    "laptimes": {"time"},
    "loan": {"loan_status", "notes", "currency_code"},
    "pitstops": {"time", "duration"},
    "qualifying": {"q1", "q2", "q3"},
    "races": {"name", "time", "url"},
    "results": {"positiontext", "time", "fastestlaptime", "fastestlapspeed"},
    "seasons": {"url"},
    "status": {"status"},
    "badges": {"name"},
    "comments": {"text", "userdisplayname"},
    "posthistory": {"revisionguid", "text", "comment", "userdisplayname"},
    "posts": {"tags"},
    "posts_backup": {"body", "title", "tags", "ownerdisplayname", "lasteditordisplayname"},
    "tags": {"tagname"},
    "appointments": {"location"},
    "clinical_status": {"other_dx", "person_neoplasm_cancer_status", "vital_status"},
    "demographics": {"gender", "race_list", "ethnicity", "country_of_birth"},
    "doctors": {"name", "gender", "department"},
    "icd_classifications": {"icd_10", "icd_o_3_site", "icd_o_3_histology"},
    "lifestyle_and_risk_factors": {
        "tobacco_smoking_history", "frequency_of_alcohol_consumption",
        "amount_of_alcohol_consumption_per_day", "antireflux_treatment_types"
    },
    "pathology_and_surgery": {
        "primary_pathology_tumor_tissue_site",
        "primary_pathology_esophageal_tumor_cental_location",
        "primary_pathology_esophageal_tumor_involvement_sites",
        "primary_pathology_histological_type",
        "primary_pathology_neoplasm_histologic_grade",
        "primary_pathology_initial_pathologic_diagnosis_method",
        "primary_pathology_init_pathology_dx_method_other",
        "primary_pathology_primary_lymph_node_presentation_assessment",
        "primary_pathology_planned_surgery_status",
        "primary_pathology_treatment_prior_to_surgery",
        "primary_pathology_residual_tumor"
    },
    "patient_addresses": {"address_type", "country_of_procurement", "state_province_of_procurement", "city_of_procurement"},
    "patient_icd_codes": {"initial_diagnosis_by"},
    "patient_staging": {
        "stage_event_clinical_stage", "stage_event_pathologic_stage", "stage_event_tnm_categories",
        "stage_event_psa", "stage_event_gleason_grading", "stage_event_ann_arbor",
        "stage_event_serum_markers", "stage_event_igcccg_stage", "stage_event_masaoka_stage"
    },
    "patients": {"patient_barcode", "tissue_source_site"},
    "staging_systems": {"stage_event_system_version"},
    "treatment_and_followup": {"primary_pathology_postoperative_rx_tx", "project"},
    "appointments": {"location"},
    "country": {"name"},
    "doctors": {"name", "gender", "department"},
    "league": {"name"},
    "match": {
        "season", "date", "goal", "shoton", "shotoff", "foulcommit", "card", "cross", "corner", "possession"
    },
    "player": {"player_name", "birthday"},
    "player_attributes": {
        "date", "preferred_foot", "attacking_work_rate", "defensive_work_rate"
    },
    "team": {"team_long_name", "team_short_name"},
    "team_attributes": {
        "date", "buildupplayspeedclass", "buildupplaydribblingclass", "buildupplaypassingclass",
        "buildupplaypositioningclass", "chancecreationpassingclass", "chancecreationcrossingclass",
        "chancecreationshootingclass", "chancecreationpositioningclass", "defencepressureclass",
        "defenceaggressionclass", "defenceteamwidthclass", "defencedefenderlineclass"
    },
    "tmpteam": {"date"},
    "account": {"frequency"},
    "client": {"gender"},
    "disp": {"type"},
    "district": {"a2", "a3", "a4", "a5", "a6", "a7"},
    "loan": {"loan_status", "notes", "currency_code", "processing_status", "external_reference_id"},
    "order": {"bank_to", "k_symbol"},
    "player_rate": {"data_source", "comments", "processing_status", "external_reference_id"},
    "trans": {"type", "operation", "k_symbol", "bank"},
    "atom": {"atom_id", "molecule_id", "element"},
    "bond": {"bond_id", "molecule_id", "bond_type"},
    "bond_list": {"bond_id", "molecule_id", "bond_type"},
    "bond_ref": {"bond_type"},
    "connected": {"atom_id", "atom_id2", "bond_id"},
    "molecule": {"molecule_id", "label"},
    "test": {"atom_id"},
     "attendance": {"link_to_event", "link_to_member"},
    "attendance_trunc": {"link_to_event", "link_to_member"},
    "budget": {"budget_id", "category", "event_status", "link_to_event"},
    "event": {"event_id", "event_name", "event_date", "type", "notes", "location", "status"},
    "expense": {"expense_id", "expense_description", "expense_date", "approved", "link_to_member", "link_to_budget"},
    "income": {"income_id", "date_received", "source", "notes", "link_to_member"},
    "major": {"major_id", "major_name", "department", "college"},
    "member": {"member_id", "first_name", "last_name", "email", "position", "t_shirt_size", "phone", "link_to_major"},
    "member_email": {"member_id", "first_name", "last_name", "email"},
    "member_position": {"full_name", "position"},
    "member_privileges": {
        "member_id", "privilege_level", "granted_by_user_id", "notes", "audit_log", "privilege_scope", "approval_status", "reference_code"
    },
    "member_trunc": {"member_id", "member_name"},
    "new_attendance": {"link_to_event", "link_to_member"},
    "zip_code": {"type", "city", "county", "state", "short_state"},
    "alignment": {"alignment"},
    "attribute": {"attribute_name"},
    "colour": {"colour"},
    "gender": {"gender"},
    "member_privileges": {
        "member_id", "privilege_level", "granted_by_user_id", "notes", "audit_log", "privilege_scope", "approval_status", "reference_code"
    },
    "publisher": {"publisher_name"},
    "race": {"race"},
    "superhero": {"superhero_name", "full_name"},
    "superpower": {"power_name"},
    "attendance_trunc": {"link_to_event", "link_to_member"},
    "examination": {"ANA Pattern", "diagnosis", "kct", "rvvt", "lac", "symptoms"},
    "laboratory": {
        "U-PRO", "crp", "ra", "rf", "rnp", "sm", "sc170", "ssa", "ssb", "centromea", "dna"
    },
    "member_trunc": {"member_id", "member_name"},
    "patient": {"sex", "admission", "diagnosis"},
    "schools":{"county","district", "school", "street", "streetabr", "city", "zip", "state", "mailstreet", "mailstrabr", "mailcity", "mailzip", "mailstate", "phone", "ext", "website"}




}



TPCH_ALIAS = {
    "supplier": "s",
    "region": "r",
    "customer": "c",
    "lineitem": "l",
    "nation": "n",
    "part": "p",
    "orders": "o",
    "partsupp": "ps"
}


DSB_ALIAS = {
    "call_center": "cc",
    "catalog_page": "cp", 
    "catalog_returns": "cr",
    "catalog_sales": "cs",
    "customer": "c",
    "customer_address": "ca",
    "customer_demographics": "cd",
    "date_dim": "d",
    "dbgen_version": "dv",
    "household_demographics": "hd",
    "income_band": "ib",
    "inventory": "inv",
    "item": "i",
    "promotion": "p",
    "reason": "r",
    "ship_mode": "sm",
    "store": "s",
    "store_returns": "sr",
    "store_sales": "ss",
    "time_dim": "t",
    "warehouse": "w",
    "web_page": "wp",
    "web_returns": "wr",
    "web_sales": "ws",
    "web_site": "web"
}

CALIFORNIA_SCHOOLS_ALIAS = {
    "schools": "s",
    "satscores": "sa"
}

CARD_GAMES_ALIAS = {
    "cards": "c",
    "card_choice": "cc",
    "card_type": "ct",
    "cards_info": "ci",
    "contents": "co",
    "foreign_data": "fd",
    "info": "i",
    "legalities": "l",
    "packages": "pa",
    "rulings": "r",
    "set_translations": "st",
    "sets": "se",
    "user_actions": "ua",
    "orders": "o",
    "card_release": "cr"
}

CODEBASE_COMMUNITY_ALIAS = {
    "users": "u",
    "badges": "b",
    "comments": "c"
}

DEBIT_CARD_SPECIALIZING_ALIAS = {
    "worker1": "w1",
    "worker2": "w2",
    "user_record": "ur",
    "orders": "o"
}

ESOPHAGEAL_ALIAS = {
    "patients": "p",
    "treatment_and_followup": "tf",
    "demographics": "d",
    "pathology_and_surgery": "ps"
}

EUROPEAN_FOOTBALL_2_ALIAS = {
    "Team": "t",
    "Team_Attributes": "ta",
    "player": "p",
    "player_attributes": "pa",
    "player_movements": "pm",
    "races": "r",
    "cards": "c",
    "user_record": "ur",
    "player_rate": "pr",
    "team_list": "tl",
    "detail": "d"
}

FINANCIAL_ALIAS = {
    "trans": "t",
    "loan": "l",
    "client": "c",
    "district": "d",
    "order": "o",
    "Product": "p",
    "ProductPrice": "pp",
    "records": "r",
    "products": "ps"
}

FORMULA_1_ALIAS = {
    "drivers": "d",
    "results": "r",
    "route": "ro",
    "route_detail": "rd",
    "route_event": "re",
    "driverstandings": "ds",
    "races": "ra",
    "constructors": "co",
    "circuits": "ci"
}

STUDENT_CLUB_ALIAS = {
    "attendance": "a",
    "event": "e",
    "budget": "b",
    "expense": "ex",
    "major": "m",
    "member": "me",
    "member_trunc": "mt",
    "member_email": "me2",
    "member_position": "mp",
    "member_privileges": "mp2",
    "zip_code": "z",
    "attendance_trunc": "at",
    "new_attendance": "na"
}

SUPERHERO_ALIAS = {
    "superhero": "s",
    "alignment": "a",
    "race": "r",
    "attribute": "at",
    "publisher": "p",
    "hero_birth_info": "hbi",
    "hero_birth_info_alt": "hbia",
    "hero_attribute": "ha"
}

THROMBOSIS_PREDICTION_ALIAS = {
    "examination": "e",
    "patient": "p",
    "laboratory": "l",
    "attribute": "a"
}

TOXICOLOGY_ALIAS = {
    "atom": "a",
    "bond": "b",
    "bond_list": "bl",
    "bond_ref": "br",
    "connected": "c",
    "molecule": "m"
}


def split_and_conditions(expr):
    if isinstance(expr, exp.And):
        return split_and_conditions(expr.left) + split_and_conditions(expr.right)
    # print("----------", expr)
    return [expr]

def get_string_column_from_from_clause(expr: exp.Expression, db_config=DB_CONFIG) -> str:
    """
    给定一个 SQL 子树（如 WHERE 节点所属的 SELECT），
    从其 FROM 表中选择一个合适的字符串字段名作为替代列。
    """

    database = db_config.get("database", "")
    if database == "dsb":
        dbname = "DSB"
    elif database == "tpch" or database == "tpch10g" or database == "tpch5g" or database == "tpch1g" or database == "tpch01g":
        dbname = "TPCH"

    DB_STRING_COLUMNS = globals().get(f"{dbname}_STRING_COLUMNS", {})
    from_clause = expr.find_ancestor(exp.Select)
    if not from_clause:
        return None

    for from_expr in from_clause.find_all(exp.Table):
        table = from_expr.name
        alias = from_expr.args.get("alias")
        table_alias = alias.name if alias else table

        if table in DB_STRING_COLUMNS:
            # col = TPCH_STRING_COLUMNS[table][0]
            col = random.choice(list(DB_STRING_COLUMNS[table]))
                # return f"{table_alias}.{col}"
            return f"{table_alias}.{col}"

    return None

def mask_all_but_one_subquery(sql: str, db_config=DB_CONFIG):
    if("with" in sql.lower()):
        # 将SQL中除了单引号内部的内容都转为小写
        def lower_except_single_quotes(s):
            result = []
            in_quote = False
            i = 0
            while i < len(s):
                c = s[i]
                if c == "'":
                    result.append(c)
                    in_quote = not in_quote
                    i += 1
                    # 处理转义单引号 ''
                    while in_quote and i < len(s) and s[i] == "'":
                        result.append(s[i])
                        i += 1
                else:
                    if in_quote:
                        result.append(c)
                    else:
                        result.append(c.lower())
                    i += 1
            return ''.join(result)
        sql = lower_except_single_quotes(sql)
        
    root = parse_one(sql)
    subqueries = OrderedDict()

    def collect_subqueries(expr, db_config=DB_CONFIG, parent=None):
        # 判断子查询是否直接作为JOIN/LEFT JOIN/FROM的子表
        if isinstance(parent, (exp.Join, exp.From)):
            return
           
        if isinstance(expr, exp.Where):
            for cond in split_and_conditions(expr.this):
                if (
                    isinstance(cond, exp.In)
                    or (isinstance(cond, exp.Not) and isinstance(cond.this, exp.In))
                    or isinstance(cond, exp.Exists)
                    or (isinstance(cond, exp.Not) and isinstance(cond.this, exp.Exists))
                ) or cond.find(exp.Subquery):
                    key = str(cond)
                    if key not in subqueries:
                        placeholder = f"__SUB_{len(subqueries)+1}__"
                        colname = get_string_column_from_from_clause(expr,db_config)
                        if colname:
                            mask_expr = parse_one(f"{colname} = '{placeholder}'")
                        else:
                            mask_expr = parse_one(f"'{placeholder}' = '{placeholder}'")
                        subqueries[key] = (cond, mask_expr)
        elif isinstance(expr, exp.Binary) and (expr.left.find(exp.Subquery) or expr.right.find(exp.Subquery)):
            key = str(expr)
            if key not in subqueries:
                placeholder = f"__SUB_{len(subqueries)+1}__"
                colname = get_string_column_from_from_clause(expr,db_config)
                if colname:
                    mask_expr = parse_one(f"{colname} = '{placeholder}'")
                else:
                    mask_expr = parse_one(f"'{placeholder}' = '{placeholder}'")
                subqueries[key] = (expr, mask_expr)
        elif isinstance(expr, exp.Subquery):
            key = str(expr)
            if key not in subqueries:
                placeholder = f"__SUB_{len(subqueries)+1}__"
                mask_expr = parse_one(f"'{placeholder}'")
                subqueries[key] = (expr, mask_expr)
        else:
            for k, v in expr.args.items():
                if isinstance(v, exp.Expression):
                    collect_subqueries(expr = v,db_config = db_config, parent =expr)
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, exp.Expression):
                            collect_subqueries(expr= item, db_config = db_config, parent=expr)

    collect_subqueries(expr = root, db_config=DB_CONFIG)

    sqls = [sql]
    sub_map = list(subqueries.items())

    for i, (keep_key, (keep_expr, _)) in enumerate(sub_map):
        tree = parse_one(sql)

        def _mask(expr):
            key = str(expr)

            # 如果只有一个子查询，则无需判断expr != keep_expr，直接mask其它即可
            if len(sub_map) == 1:
                if key in subqueries:
                    return subqueries[key][1]
            else:
                if key in subqueries and expr != keep_expr:
                    return subqueries[key][1]  # 已经提前构造好的 mask_expr

            for k, v in expr.args.items():
                if isinstance(v, exp.Expression):
                    expr.set(k, _mask(v))
                elif isinstance(v, list):
                    expr.set(k, [_mask(item) if isinstance(item, exp.Expression) else item for item in v])
            return expr

        masked_tree = _mask(tree)
        if(len(sub_map) == 1):
            # 如果只有一个子查询，则直接使用原始的 mask_expr
            sqls.append(sql)
        else:
            sqls.append(masked_tree.sql())

    subquery_map = [(v[0].sql(), v[1].sql()) for v in subqueries.values()]
    # print("==masked_queries:", sqls)
    # print("==subquery_map:", subquery_map)
    return sqls, subquery_map



def get_alias_to_full(db_config):
    """
    Return a mapping from table alias to full table name for the current database, based on db_config['database'].
    """
    db_id = db_config.get("database", "").upper()
    if(db_id == "TPCH10G") or (db_id == "TPCH1G") or (db_id == "TPCH5G"):
        db_id = "TPCH"
    # print("==db_id:", db_id)
    alias_dict_name = f"{db_id}_ALIAS"
    # 获取全局变量中的别名映射字典
    alias_dict = globals().get(alias_dict_name)
    # print("==alias_dict:", alias_dict)
    if not alias_dict:
        return {}
        # raise ValueError(f"未找到数据库别名映射: {alias_dict_name}")
    return {v: k for k, v in alias_dict.items()}

def restore_placeholders(masked_sql: str, subquery_map: list, db_config) -> str:
    """
    Restore the masked SQL by replacing mask expressions with the original subquery conditions.
    1. Replace aliases in mask conditions with full table names (e.g., l. → lineitem.).
    2. After replacement, avoid double prefixes like lineitem.lineitem.col; keep as lineitem.col.
    """
    restored_sql = masked_sql

    # 构造反向映射: 别名 -> 全名
    # alias_to_full = {v: k for k, v in TPCH_ALIAS.items()}
    alias_to_full = get_alias_to_full(db_config)
    # print("==alias_to_full:", alias_to_full)

    for original_sql, mask_cond in subquery_map:
        # print("~~~~~~~~~")
        for alias, full_name in alias_to_full.items():
            original_sql = original_sql.replace(f" {alias}.", f" {full_name}.")
            if original_sql.startswith(f"{alias}."):
                original_sql = original_sql.replace(f"{alias}.", f"{full_name}.")
            elif(original_sql.startswith(f"({alias}.")):
                original_sql = original_sql.replace(f"({alias}.", f"({full_name}.")
        #mask_cond选取第一个.后面的部分
        mask_cond = mask_cond.split(".", 1)[-1]
        
        database = db_config.get("database", "")
        if database == "dsb":
            dbname = "DSB"
        elif database == "tpch" or database == "tpch10g" or database == "tpch5g" or database == "tpch1g":
            dbname = "TPCH"
        
        DB_STRING_COLUMNS = globals().get(f"{dbname}_STRING_COLUMNS", {})
        orig_first_word = original_sql.strip().split()[0]
        # Try to find the table name from the mask_cond context
        for table_name in DB_STRING_COLUMNS:
            if orig_first_word not in DB_STRING_COLUMNS.get(table_name, set()):
                for match in re.finditer(re.escape(mask_cond), restored_sql):
                    start = match.start()
                    # 检查mask_cond前面是否为 table_name.
                    # col_name 应该是表名
                    col_name = table_name
                    tab_dot = f"{col_name}."
                    if restored_sql[max(0, start-len(tab_dot)):start] == tab_dot:
                        # 删除 col_name.
                        restored_sql = restored_sql[:start-len(tab_dot)] + restored_sql[start:]
                        break
                    else:
                        # 如果是 xx.，则删除 .和前面这个单词
                        prefix = restored_sql[:start]
                        m = re.search(r"(\w+)\.$", prefix)
                        if m:
                            # 删除 .和前面这个单词
                            restored_sql = restored_sql[:m.start()] + restored_sql[start:]
                            break



        # 替换 mask_cond 到 SQL 中，括号优先
        restored_sql = restored_sql.replace(f"({mask_cond})", f"({original_sql})")
        restored_sql = restored_sql.replace(mask_cond, original_sql)

    # 清除如 lineitem.l.col 这种双重前缀 => lineitem.col
    # 正则匹配类似 lineitem.l.col → 保留 lineitem.col
    restored_sql = re.sub(r"\b(\w+)\.(\w+)\.(\w+)", lambda m: f"{m.group(1)}.{m.group(3)}", restored_sql)

    print("==restored_sql:", restored_sql)
    return restored_sql





if __name__ == "__main__":

    sql_query = """SELECT * FROM (SELECT * FROM (SELECT orders.o_orderkey, orders.o_custkey, orders.o_orderstatus, orders.o_totalprice, orders.o_orderdate, orders.o_orderpriority, orders.o_clerk, orders.o_shippriority, orders.o_comment FROM orders, lineitem WHERE orders.o_orderkey > lineitem.l_orderkey AND (orders.o_orderkey < 200000 AND lineitem.l_orderkey < 50000) AND (lineitem.l_quantity > 5 AND (lineitem.l_shipdate >= DATE '1995-01-01' AND lineitem.l_shipdate <= DATE '1995-12-31'))) AS t0 INNER JOIN customer ON t0.o_custkey = customer.c_custkey UNION ALL SELECT * FROM (SELECT o_orderkey, o_custkey, o_orderstatus, o_totalprice, o_orderdate, o_orderpriority, o_clerk, o_shippriority, o_comment FROM (SELECT t1.o_orderkey, t1.o_custkey, t1.o_orderstatus, t1.o_totalprice, t1.o_orderdate, t1.o_orderpriority, t1.o_clerk, t1.o_shippriority, t1.o_comment, nation.n_nationkey, nation.n_name, nation.n_regionkey, nation.n_comment FROM (SELECT o_orderkey, o_custkey, o_orderstatus, o_totalprice, o_orderdate, o_orderpriority, o_clerk, o_shippriority, o_comment, o_custkey + 25 AS f9 FROM orders) AS t1 INNER JOIN nation ON t1.f9 = nation.n_nationkey) AS t2 WHERE t2.o_orderkey > 1000 AND (t2.n_name = 'UNITED STATES' OR t2.n_name = 'CANADA' OR t2.n_name = 'GERMANY') AND t2.o_orderkey > 1000000) AS t4 INNER JOIN customer AS customer0 ON t4.o_custkey = customer0.c_custkey) AS t5 WHERE c_custkey > 2000"""
    extracted_result = extract_and_fix_subqueries(sql_query)
    fixed_subqueries = extracted_result["fixed_subqueries"]
    print("======")
    fixed_sqls = []
    for j, (original, fixed) in enumerate(fixed_subqueries, 1):
        print(f"-----------\nSubquery {j}:")
        print(f"  Original: {original}")
        print(f"  Fixed: {fixed}")
        fixed_sqls.append(fixed)

        sqls, subqueries = mask_all_but_one_subquery(fixed)

        for i, s in enumerate(sqls):
            print(f"\n\n--- Masked SQL {i} ---")
            print(s)
    
            print("\n\n")
            restored = restore_placeholders(s, subqueries, db_config=DB_CONFIG)
            # print("\n[还原后 SQL]:\n", restored)
    # print(subqueries)

    