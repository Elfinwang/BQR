with table1 as (select table4.col1,table4.col2,table4.col3,table4.col4,table4.col5,table4.col6,col9,col24,col25,col10,col12,col11 from table3 col27 inner join (select col8 from table5 where (table5.col7 = '4a86a8c2-3f4f-425e-9a8c-b72531094a16' or table5.col7 = '4da201f3-6750-49de-b57f-8970759fc0e0') group by col8) col28 on ((table5.col8 = table4.col6))  where table4.col1 > '2023-10-09 00:00:00' and table4.col1 <= '2023-10-16 00:00:00' and ((table4.col1 > '2023-10-09 09:00:00' and table4.col1 <= '2023-10-09 13:00:00')) and ( table4.col1 > '2023-10-09 09:00:00' and table4.col1 <= '2023-10-09 13:00:00' ) group by table4.col1,table4.col2,table4.col3,table4.col4,table4.col5,table4.col6,col9,col24,col25,col10,col12,col11),col29 as (select distinct col1,col2,col4,col6,col9,col10 from table1 col27) 

select
  col1 - interval '60' col30 as table7,
  col1 as table8,
  col3,
  col4,
  col2,
  (
    (
      case
        when cast(col31 as varchar) = '__UDF_PLACEHOLDER_0__'
        then 0
        else col31
      end
    ) + (
      0 * coalesce(col32, 0)
    ) + (
      0 * coalesce(col33, 0)
    ) + (
      0 * coalesce(col34, 0)
    )
  ) as table9,
  (
    (
      case
        when cast(col31 as varchar) = '__UDF_PLACEHOLDER_1__'
        then 0
        else col31
      end
    ) + (
      0 * coalesce(col32, 0)
    ) + (
      0 * coalesce(col33, 0)
    ) + (
      0 * coalesce(col34, 0)
    )
  ) as table10,
  col31,
  (
    (
      case
        when cast(col35 as varchar) = '__UDF_PLACEHOLDER_2__'
        then 0
        else col35
      end
    ) + (
      0 * coalesce(col36, 0)
    )
  ) as table11,
  (
    (
      case
        when cast(col37 as varchar) = '__UDF_PLACEHOLDER_3__'
        then 0
        else col37
      end
    ) + (
      0 * coalesce(col35, 0)
    ) + (
      0 * coalesce(col38, 0)
    ) + (
      0 * coalesce(col36, 0)
    )
  ) as table12,
  (
    (
      case
        when cast(col38 as varchar) = '__UDF_PLACEHOLDER_4__'
        then 0
        else col38
      end
    ) + (
      0 * coalesce(col36, 0)
    )
  ) as table13,
  (
    (
      case
        when cast(col37 as varchar) = '__UDF_PLACEHOLDER_5__'
        then 0
        else col37
      end
    ) + (
      0 * coalesce(col35, 0)
    )
  ) as table14,
  (
    (
      case
        when cast(col39 as varchar) = '__UDF_PLACEHOLDER_6__'
        then 0
        else col39
      end
    ) + (
      0 * coalesce(col40, 0)
    ) + (
      0 * coalesce(col41, 0)
    ) + (
      0 * coalesce(col42, 0)
    ) + (
      0 * coalesce(col43, 0)
    )
  ) as table15,
  (
    (
      case
        when cast(col42 as varchar) = '__UDF_PLACEHOLDER_7__'
        then 0
        else col42
      end
    ) + (
      0 * coalesce(col40, 0)
    ) + (
      0 * coalesce(col43, 0)
    )
  ) as table16,
  (
    (
      case
        when cast(col42 as varchar) = '__UDF_PLACEHOLDER_8__'
        then 0
        else col42
      end
    ) + (
      0 * coalesce(col40, 0)
    )
  ) as table17,
  (
    (
      case
        when cast(col42 as varchar) = '__UDF_PLACEHOLDER_9__'
        then 0
        else col42
      end
    ) + (
      0 * coalesce(col40, 0)
    ) + (
      0 * coalesce(col44, 0)
    ) + (
      0 * coalesce(col45, 0)
    ) + (
      0 * coalesce(col46, 0)
    ) + (
      0 * coalesce(col47, 0)
    )
  ) as table18,
  (
    (
      case
        when cast(col48 as varchar) = '__UDF_PLACEHOLDER_10__'
        then 0
        else col48
      end
    ) + (
      0 * coalesce(col49, 0)
    ) + (
      0 * coalesce(col50, 0)
    ) + (
      0 * coalesce(col51, 0)
    ) + (
      0 * coalesce(col52, 0)
    ) + (
      0 * coalesce(col53, 0)
    ) + (
      0 * coalesce(col54, 0)
    ) + (
      0 * coalesce(col55, 0)
    ) + (
      0 * coalesce(col56, 0)
    ) + (
      0 * coalesce(col57, 0)
    ) + (
      0 * coalesce(col58, 0)
    ) + (
      0 * coalesce(col59, 0)
    )
  ) as table19,
  (
    (
      case
        when cast(col44 as varchar) = '__UDF_PLACEHOLDER_11__'
        then 0
        else col44
      end
    ) + (
      0 * coalesce(col39, 0)
    ) + (
      0 * coalesce(col60, 0)
    ) + (
      0 * coalesce(col61, 0)
    ) + (
      0 * coalesce(col62, 0)
    ) + (
      0 * coalesce(col63, 0)
    ) + (
      0 * coalesce(col41, 0)
    ) + (
      0 * coalesce(col42, 0)
    ) + (
      0 * coalesce(col40, 0)
    ) + (
      0 * coalesce(col45, 0)
    ) + (
      0 * coalesce(col46, 0)
    )
  ) as table20,
  (
    (
      case
        when cast(col64 as varchar) = '__UDF_PLACEHOLDER_12__'
        then 0
        else col64
      end
    ) + (
      0 * coalesce(col31, 0)
    )
  ) as table21,
  col65,
  col66,
  col67,
  col68,
  col69,
  col70,
  col71,
  col72,
  (
    case
      when cast(col73 as varchar) = '__UDF_PLACEHOLDER_13__'
      then 0
      else col73
    end
  ) as table22,
  (
    case
      when cast(col74 as varchar) = '__UDF_PLACEHOLDER_14__'
      then 0
      else col74
    end
  ) as table23,
  col75,
  col76,
  col77,
  col78,
  (
    (
      case
        when cast(col79 as varchar) = '__UDF_PLACEHOLDER_15__'
        then 0
        else col79
      end
    ) + (
      0 * coalesce(col80, 0)
    )
  ) as table24,
  (
    (
      case
        when cast(col81 as varchar) = '__UDF_PLACEHOLDER_16__'
        then 0
        else col81
      end
    ) + (
      0 * coalesce(col82, 0)
    )
  ) as table25,
  (
    cast((
      (
        case
          when cast(col79 as varchar) = '__UDF_PLACEHOLDER_17__'
          then 0
          else col79
        end
      ) + (
        0 * coalesce(col83, 0)
      ) + (
        0 * coalesce(col84, 0)
      )
    ) as varchar) || cast((
      (
        case
          when cast(col80 as varchar) = '__UDF_PLACEHOLDER_18__'
          then 0
          else col80
        end
      ) + (
        0 * coalesce(col83, 0)
      ) + (
        0 * coalesce(col84, 0)
      )
    ) as varchar) || '__UDF_PLACEHOLDER_19__'
  ) as table26,
  (
    (
      case
        when cast(col85 as varchar) = '__UDF_PLACEHOLDER_20__'
        then 0
        else col85
      end
    ) + (
      0 * coalesce(col86, 0)
    )
  ) as table27,
  (
    (
      case
        when cast(col87 as varchar) = '__UDF_PLACEHOLDER_21__'
        then 0
        else col87
      end
    ) + (
      0 * coalesce(col80, 0)
    )
  ) as table28,
  (
    (
      case
        when cast(col88 as varchar) = '__UDF_PLACEHOLDER_22__'
        then 0
        else col88
      end
    ) + (
      0 * coalesce(col82, 0)
    )
  ) as table29,
  (
    (
      case
        when cast(col89 as varchar) = '__UDF_PLACEHOLDER_23__'
        then 0
        else col89
      end
    ) + (
      0 * coalesce(col90, 0)
    ) + (
      0 * coalesce(col91, 0)
    )
  ) as table30,
  (
    (
      case
        when cast(col92 as varchar) = '__UDF_PLACEHOLDER_24__'
        then 0
        else col92
      end
    ) + (
      0 * coalesce(col93, 0)
    ) + (
      0 * coalesce(col94, 0)
    )
  ) as table31,
  (
    (
      case
        when cast(col92 as varchar) = '__UDF_PLACEHOLDER_25__'
        then 0
        else col92
      end
    ) + (
      0 * coalesce(col94, 0)
    )
  ) as table32,
  (
    case
      when cast(col95 as varchar) = '__UDF_PLACEHOLDER_26__'
      then 0
      else col95
    end
  ) as table33,
  (
    case
      when cast(col96 as varchar) = '__UDF_PLACEHOLDER_27__'
      then 0
      else col96
    end
  ) as table34,
  (
    (
      case
        when cast(col97 as varchar) = '__UDF_PLACEHOLDER_28__'
        then 0
        else col97
      end
    ) + (
      0 * coalesce(col98, 0)
    )
  ) as table35,
  (
    (
      case
        when cast(col99 as varchar) = '__UDF_PLACEHOLDER_29__'
        then 0
        else col99
      end
    ) + (
      0 * coalesce(col100, 0)
    )
  ) as table36,
  (
    (
      case
        when cast(col101 as varchar) = '__UDF_PLACEHOLDER_30__'
        then 0
        else col101
      end
    ) + (
      0 * coalesce(col102, 0)
    )
  ) as table37,
  (
    (
      case
        when cast(col103 as varchar) = '__UDF_PLACEHOLDER_31__'
        then 0
        else col103
      end
    ) + (
      0 * coalesce(col104, 0)
    )
  ) as table38,
  (
    (
      case
        when cast(col105 as varchar) = '__UDF_PLACEHOLDER_32__'
        then 0
        else col105
      end
    ) + (
      0 * coalesce(col106, 0)
    ) + (
      0 * coalesce(col107, 0)
    )
  ) as table39,
  (
    (
      case
        when cast(col108 as varchar) = '__UDF_PLACEHOLDER_33__'
        then 0
        else col108
      end
    ) + (
      0 * coalesce(col106, 0)
    ) + (
      0 * coalesce(col107, 0)
    )
  ) as table40,
  (
    (
      case
        when cast(col109 as varchar) = '__UDF_PLACEHOLDER_34__'
        then 0
        else col109
      end
    ) + (
      0 * coalesce(col110, 0)
    )
  ) as table41,
  (
    (
      case
        when cast(col111 as varchar) = '__UDF_PLACEHOLDER_35__'
        then 0
        else col111
      end
    ) + (
      0 * coalesce(col112, 0)
    )
  ) as table42,
  (
    (
      case
        when cast(col113 as varchar) = '__UDF_PLACEHOLDER_36__'
        then 0
        else col113
      end
    ) + (
      0 * coalesce(col87, 0)
    )
  ) as table43,
  (
    (
      case
        when cast(col114 as varchar) = '__UDF_PLACEHOLDER_37__'
        then 0
        else col114
      end
    ) + (
      0 * coalesce(col88, 0)
    )
  ) as table44,
  (
    (
      case
        when cast(col115 as varchar) = '__UDF_PLACEHOLDER_38__'
        then 0
        else col115
      end
    ) + (
      0 * coalesce(col116, 0)
    )
  ) as table45,
  (
    (
      case
        when cast(col117 as varchar) = '__UDF_PLACEHOLDER_39__'
        then 0
        else col117
      end
    ) + (
      0 * coalesce(col118, 0)
    )
  ) as table46,
  (
    (
      case
        when cast(col119 as varchar) = '__UDF_PLACEHOLDER_40__'
        then 0
        else col119
      end
    ) + (
      0 * coalesce(col120, 0)
    )
  ) as table47,
  (
    (
      case
        when cast(col121 as varchar) = '__UDF_PLACEHOLDER_41__'
        then 0
        else col121
      end
    ) + (
      0 * coalesce(col120, 0)
    )
  ) as table48,
  (
    (
      case
        when cast(col122 as varchar) = '__UDF_PLACEHOLDER_42__'
        then 0
        else col122
      end
    ) + (
      0 * coalesce(col123, 0)
    )
  ) as table49,
  (
    (
      case
        when cast(col124 as varchar) = '__UDF_PLACEHOLDER_43__'
        then 0
        else col124
      end
    ) + (
      0 * coalesce(col125, 0)
    )
  ) as table50,
  (
    (
      case
        when cast(col126 as varchar) = '__UDF_PLACEHOLDER_44__'
        then 0
        else col126
      end
    ) + (
      0 * coalesce(col125, 0)
    )
  ) as table51,
  (
    (
      case
        when cast(col127 as varchar) = '__UDF_PLACEHOLDER_45__'
        then 0
        else col127
      end
    ) + (
      0 * coalesce(col128, 0)
    )
  ) as table52,
  (
    (
      case
        when cast(col129 as varchar) = '__UDF_PLACEHOLDER_46__'
        then 0
        else col129
      end
    ) + (
      0 * coalesce(col130, 0)
    )
  ) as table53,
  (
    (
      case
        when cast(col131 as varchar) = '__UDF_PLACEHOLDER_47__'
        then 0
        else col131
      end
    ) + (
      0 * coalesce(col132, 0)
    ) + (
      0 * coalesce(col133, 0)
    ) + (
      0 * coalesce(col134, 0)
    )
  ) as table54,
  (
    (
      case
        when cast(col135 as varchar) = '__UDF_PLACEHOLDER_48__'
        then 0
        else col135
      end
    ) + (
      0 * coalesce(col136, 0)
    )
  ) as table55,
  (
    (
      case
        when cast(col137 as varchar) = '__UDF_PLACEHOLDER_49__'
        then 0
        else col137
      end
    ) + (
      0 * coalesce(col138, 0)
    ) + (
      0 * coalesce(col139, 0)
    ) + (
      0 * coalesce(col140, 0)
    ) + (
      0 * coalesce(col141, 0)
    )
  ) as table56,
  (
    (
      case
        when cast(col142 as varchar) = '__UDF_PLACEHOLDER_50__'
        then 0
        else col142
      end
    ) + (
      0 * coalesce(col143, 0)
    )
  ) as table57,
  (
    (
      case
        when cast(col144 as varchar) = '__UDF_PLACEHOLDER_51__'
        then 0
        else col144
      end
    ) + (
      0 * coalesce(col145, 0)
    )
  ) as table58,
  (
    (
      case
        when cast(col146 as varchar) = '__UDF_PLACEHOLDER_52__'
        then 0
        else col146
      end
    ) + (
      0 * coalesce(col147, 0)
    )
  ) as table59,
  (
    (
      case
        when cast(col148 as varchar) = '__UDF_PLACEHOLDER_53__'
        then 0
        else col148
      end
    ) + (
      0 * coalesce(col147, 0)
    )
  ) as table60,
  (
    (
      case
        when cast(col149 as varchar) = '__UDF_PLACEHOLDER_54__'
        then 0
        else col149
      end
    ) + (
      0 * coalesce(col147, 0)
    )
  ) as table61,
  (
    (
      case
        when cast(col150 as varchar) = '__UDF_PLACEHOLDER_55__'
        then 0
        else col150
      end
    ) + (
      0 * coalesce(col147, 0)
    )
  ) as table62,
  (
    (
      case
        when cast(col151 as varchar) = '__UDF_PLACEHOLDER_56__'
        then 0
        else col151
      end
    ) + (
      0 * coalesce(col136, 0)
    )
  ) as table63,
  (
    (
      case
        when cast(col152 as varchar) = '__UDF_PLACEHOLDER_57__'
        then 0
        else col152
      end
    ) + (
      0 * coalesce(col136, 0)
    )
  ) as table64,
  (
    (
      case
        when cast(col153 as varchar) = '__UDF_PLACEHOLDER_58__'
        then 0
        else col153
      end
    ) + (
      0 * coalesce(col136, 0)
    )
  ) as table65,
  (
    (
      case
        when cast(col154 as varchar) = '__UDF_PLACEHOLDER_59__'
        then 0
        else col154
      end
    ) + (
      0 * coalesce(col136, 0)
    )
  ) as table66,
  (
    (
      case
        when cast(col138 as varchar) = '__UDF_PLACEHOLDER_60__'
        then 0
        else col138
      end
    ) + (
      0 * coalesce(col139, 0)
    ) + (
      0 * coalesce(col140, 0)
    ) + (
      0 * coalesce(col141, 0)
    )
  ) as table67,
  (
    (
      case
        when cast(col139 as varchar) = '__UDF_PLACEHOLDER_61__'
        then 0
        else col139
      end
    ) + (
      0 * coalesce(col138, 0)
    ) + (
      0 * coalesce(col140, 0)
    ) + (
      0 * coalesce(col141, 0)
    )
  ) as table68,
  (
    (
      case
        when cast(col140 as varchar) = '__UDF_PLACEHOLDER_62__'
        then 0
        else col140
      end
    ) + (
      0 * coalesce(col138, 0)
    ) + (
      0 * coalesce(col139, 0)
    ) + (
      0 * coalesce(col141, 0)
    )
  ) as table69,
  (
    (
      case
        when cast(col141 as varchar) = '__UDF_PLACEHOLDER_63__'
        then 0
        else col141
      end
    ) + (
      0 * coalesce(col138, 0)
    ) + (
      0 * coalesce(col139, 0)
    ) + (
      0 * coalesce(col140, 0)
    )
  ) as table70,
  (
    (
      case
        when cast(col155 as varchar) = '__UDF_PLACEHOLDER_64__'
        then 0
        else col155
      end
    ) + (
      0 * coalesce(col156, 0)
    ) + (
      0 * coalesce(col106, 0)
    ) + (
      0 * coalesce(col157, 0)
    )
  ) as table71,
  (
    (
      case
        when cast(col158 as varchar) = '__UDF_PLACEHOLDER_65__'
        then 0
        else col158
      end
    ) + (
      0 * coalesce(col159, 0)
    ) + (
      0 * coalesce(col106, 0)
    ) + (
      0 * coalesce(col160, 0)
    )
  ) as table72,
  (
    (
      case
        when cast(col161 as varchar) = '__UDF_PLACEHOLDER_66__'
        then 0
        else col161
      end
    ) + (
      0 * coalesce(col162, 0)
    )
  ) as table73,
  (
    (
      case
        when cast(col163 as varchar) = '__UDF_PLACEHOLDER_67__'
        then 0
        else col163
      end
    ) + (
      0 * coalesce(col164, 0)
    )
  ) as table74,
  (
    (
      case
        when cast(col165 as varchar) = '__UDF_PLACEHOLDER_68__'
        then 0
        else col165
      end
    ) + (
      0 * coalesce(col166, 0)
    )
  ) as table75,
  (
    (
      case
        when cast(col167 as varchar) = '__UDF_PLACEHOLDER_69__'
        then 0
        else col167
      end
    ) + (
      0 * coalesce(col168, 0)
    )
  ) as table76,
  (
    (
      case
        when cast(col169 as varchar) = '__UDF_PLACEHOLDER_70__'
        then 0
        else col169
      end
    ) + (
      0 * coalesce(col170, 0)
    )
  ) as table77,
  (
    cast((
      (
        case
          when cast(col161 as varchar) = '__UDF_PLACEHOLDER_71__'
          then 0
          else col161
        end
      ) + (
        0 * coalesce(col162, 0)
      )
    ) as varchar) || cast((
      (
        case
          when cast(col165 as varchar) = '__UDF_PLACEHOLDER_72__'
          then 0
          else col165
        end
      ) + (
        0 * coalesce(col166, 0)
      )
    ) as varchar) || cast((
      (
        case
          when cast(col169 as varchar) = '__UDF_PLACEHOLDER_73__'
          then 0
          else col169
        end
      ) + (
        0 * coalesce(col170, 0)
      )
    ) as varchar) || '__UDF_PLACEHOLDER_74__'
  ) as table78,
  (
    (
      case
        when cast(col161 as varchar) = '__UDF_PLACEHOLDER_75__'
        then 0
        else col161
      end
    ) + (
      0 * coalesce(col162, 0)
    ) + (
      0 * coalesce(col165, 0)
    ) + (
      0 * coalesce(col166, 0)
    ) + (
      0 * coalesce(col167, 0)
    ) + (
      0 * coalesce(col168, 0)
    )
  ) as table79,
  (
    (
      case
        when cast(col171 as varchar) = '__UDF_PLACEHOLDER_76__'
        then 0
        else col171
      end
    ) + (
      0 * coalesce(col172, 0)
    )
  ) as table80,
  (
    (
      case
        when cast(col173 as varchar) = '__UDF_PLACEHOLDER_77__'
        then 0
        else col173
      end
    ) + (
      0 * coalesce(col174, 0)
    )
  ) as table81,
  (
    (
      case
        when cast(col175 as varchar) = '__UDF_PLACEHOLDER_78__'
        then 0
        else col175
      end
    ) + (
      0 * coalesce(col176, 0)
    )
  ) as table82,
  (
    (
      case
        when cast(col177 as varchar) = '__UDF_PLACEHOLDER_79__'
        then 0
        else col177
      end
    ) + (
      0 * coalesce(col178, 0)
    ) + (
      0 * coalesce(col179, 0)
    ) + (
      0 * coalesce(col180, 0)
    ) + (
      0 * coalesce(col181, 0)
    ) + (
      0 * coalesce(col182, 0)
    ) + (
      0 * coalesce(col183, 0)
    ) + (
      0 * coalesce(col184, 0)
    ) + (
      0 * coalesce(col185, 0)
    ) + (
      0 * coalesce(col186, 0)
    ) + (
      0 * coalesce(col187, 0)
    ) + (
      0 * coalesce(col188, 0)
    ) + (
      0 * coalesce(col189, 0)
    )
  ) as table83,
  (
    (
      case
        when cast(col190 as varchar) = '__UDF_PLACEHOLDER_80__'
        then 0
        else col190
      end
    ) + (
      0 * coalesce(col191, 0)
    )
  ) as table84,
  (
    (
      case
        when cast(col192 as varchar) = '__UDF_PLACEHOLDER_81__'
        then 0
        else col192
      end
    ) + (
      0 * coalesce(col173, 0)
    ) + (
      0 * coalesce(col193, 0)
    ) + (
      0 * coalesce(col194, 0)
    ) + (
      0 * coalesce(col195, 0)
    ) + (
      0 * coalesce(col196, 0)
    ) + (
      0 * coalesce(col197, 0)
    ) + (
      0 * coalesce(col198, 0)
    ) + (
      0 * coalesce(col199, 0)
    ) + (
      0 * coalesce(col200, 0)
    ) + (
      0 * coalesce(col201, 0)
    )
  ) as table85,
  (
    (
      case
        when cast(col202 as varchar) = '__UDF_PLACEHOLDER_82__'
        then 0
        else col202
      end
    ) + (
      0 * coalesce(col203, 0)
    ) + (
      0 * coalesce(col204, 0)
    ) + (
      0 * coalesce(col205, 0)
    ) + (
      0 * coalesce(col206, 0)
    ) + (
      0 * coalesce(col207, 0)
    ) + (
      0 * coalesce(col208, 0)
    ) + (
      0 * coalesce(col209, 0)
    ) + (
      0 * coalesce(col210, 0)
    ) + (
      0 * coalesce(col211, 0)
    ) + (
      0 * coalesce(col212, 0)
    ) + (
      0 * coalesce(col213, 0)
    ) + (
      0 * coalesce(col214, 0)
    ) + (
      0 * coalesce(col215, 0)
    ) + (
      0 * coalesce(col216, 0)
    )
  ) as table86,
  (
    (
      case
        when cast(col217 as varchar) = '__UDF_PLACEHOLDER_83__'
        then 0
        else col217
      end
    ) + (
      0 * coalesce(col218, 0)
    ) + (
      0 * coalesce(col219, 0)
    )
  ) as table87,
  (
    (
      case
        when cast(col220 as varchar) = '__UDF_PLACEHOLDER_84__'
        then 0
        else col220
      end
    ) + (
      0 * coalesce(col221, 0)
    ) + (
      0 * coalesce(col222, 0)
    )
  ) as table88,
  (
    (
      case
        when cast(col222 as varchar) = '__UDF_PLACEHOLDER_85__'
        then 0
        else col222
      end
    ) + (
      0 * coalesce(col161, 0)
    )
  ) as table89,
  (
    (
      case
        when cast(col223 as varchar) = '__UDF_PLACEHOLDER_86__'
        then 0
        else col223
      end
    ) + (
      0 * coalesce(col224, 0)
    ) + (
      0 * coalesce(col225, 0)
    ) + (
      0 * coalesce(col226, 0)
    ) + (
      0 * coalesce(col227, 0)
    ) + (
      0 * coalesce(col228, 0)
    ) + (
      0 * coalesce(col229, 0)
    ) + (
      0 * coalesce(col230, 0)
    )
  ) as table90,
  (
    (
      case
        when cast(col231 as varchar) = '__UDF_PLACEHOLDER_87__'
        then 0
        else col231
      end
    ) + (
      0 * coalesce(col232, 0)
    ) + (
      0 * coalesce(col233, 0)
    ) + (
      0 * coalesce(col234, 0)
    ) + (
      0 * coalesce(col235, 0)
    ) + (
      0 * coalesce(col236, 0)
    ) + (
      0 * coalesce(col237, 0)
    ) + (
      0 * coalesce(col238, 0)
    )
  ) as table91,
  (
    (
      case
        when cast(col231 as varchar) = '__UDF_PLACEHOLDER_88__'
        then 0
        else col231
      end
    ) + (
      0 * coalesce(col233, 0)
    ) + (
      0 * coalesce(col235, 0)
    ) + (
      0 * coalesce(col237, 0)
    )
  ) as table92,
  (
    (
      case
        when cast(col232 as varchar) = '__UDF_PLACEHOLDER_89__'
        then 0
        else col232
      end
    ) + (
      0 * coalesce(col234, 0)
    ) + (
      0 * coalesce(col236, 0)
    ) + (
      0 * coalesce(col238, 0)
    )
  ) as table93,
  (
    (
      case
        when cast(col239 as varchar) = '__UDF_PLACEHOLDER_90__'
        then 0
        else col239
      end
    ) + (
      0 * coalesce(col240, 0)
    )
  ) as table94,
  (
    (
      case
        when cast(col196 as varchar) = '__UDF_PLACEHOLDER_91__'
        then 0
        else col196
      end
    ) + (
      0 * coalesce(col241, 0)
    )
  ) as table95,
  (
    (
      case
        when cast(col242 as varchar) = '__UDF_PLACEHOLDER_92__'
        then 0
        else col242
      end
    ) + (
      0 * coalesce(col243, 0)
    )
  ) as table96,
  (
    (
      case
        when cast(col235 as varchar) = '__UDF_PLACEHOLDER_93__'
        then 0
        else col235
      end
    ) + (
      0 * coalesce(col237, 0)
    ) + (
      0 * coalesce(col236, 0)
    ) + (
      0 * coalesce(col238, 0)
    )
  ) as table97,
  (
    (
      case
        when cast(col244 as varchar) = '__UDF_PLACEHOLDER_94__'
        then 0
        else col244
      end
    ) + (
      0 * coalesce(col245, 0)
    )
  ) as table98,
  (
    (
      case
        when cast(col246 as varchar) = '__UDF_PLACEHOLDER_95__'
        then 0
        else col246
      end
    ) + (
      0 * coalesce(col247, 0)
    )
  ) as table99,
  (
    (
      case
        when cast(col44 as varchar) = '__UDF_PLACEHOLDER_96__'
        then 0
        else col44
      end
    ) + (
      0 * coalesce(col248, 0)
    ) + (
      0 * coalesce(col249, 0)
    ) + (
      0 * coalesce(col43, 0)
    ) + (
      0 * coalesce(col191, 0)
    )
  ) as table100,
  col250,
  col251,
  (
    (
      case
        when cast(col252 as varchar) = '__UDF_PLACEHOLDER_97__'
        then 0
        else col252
      end
    ) + (
      0 * coalesce(col161, 0)
    )
  ) as table101,
  (
    (
      case
        when cast(col253 as varchar) = '__UDF_PLACEHOLDER_98__'
        then 0
        else col253
      end
    ) + (
      0 * coalesce(col254, 0)
    )
  ) as table102,
  col255,
  (
    (
      case
        when cast(col256 as varchar) = '__UDF_PLACEHOLDER_99__'
        then 0
        else col256
      end
    ) + (
      0 * coalesce(col257, 0)
    )
  ) as table103,
  (
    (
      case
        when cast(col258 as varchar) = '__UDF_PLACEHOLDER_100__'
        then 0
        else col258
      end
    ) + (
      0 * coalesce(col259, 0)
    )
  ) as table104,
  col260,
  col261,
  col262,
  col263,
  (
    (
      case
        when cast(col264 as varchar) = '__UDF_PLACEHOLDER_101__'
        then 0
        else col264
      end
    ) + (
      0 * coalesce(col265, 0)
    ) + (
      0 * coalesce(col266, 0)
    ) + (
      0 * coalesce(col267, 0)
    )
  ) as table105,
  (
    (
      case
        when cast(col268 as varchar) = '__UDF_PLACEHOLDER_102__'
        then 0
        else col268
      end
    ) + (
      0 * coalesce(col269, 0)
    ) + (
      0 * coalesce(col270, 0)
    ) + (
      0 * coalesce(col271, 0)
    )
  ) as table106,
  (
    (
      case
        when cast(col272 as varchar) = '__UDF_PLACEHOLDER_103__'
        then 0
        else col272
      end
    ) + (
      0 * coalesce(col273, 0)
    )
  ) as table107,
  (
    (
      case
        when cast(col274 as varchar) = '__UDF_PLACEHOLDER_104__'
        then 0
        else col274
      end
    ) + (
      0 * coalesce(col147, 0)
    )
  ) as table108,
  (
    (
      case
        when cast(col275 as varchar) = '__UDF_PLACEHOLDER_105__'
        then 0
        else col275
      end
    ) + (
      0 * coalesce(col276, 0)
    ) + (
      0 * coalesce(col277, 0)
    ) + (
      0 * coalesce(col278, 0)
    )
  ) as table109,
  (
    (
      case
        when cast(col279 as varchar) = '__UDF_PLACEHOLDER_106__'
        then 0
        else col279
      end
    ) + (
      0 * coalesce(col280, 0)
    )
  ) as table110,
  (
    (
      case
        when cast(col281 as varchar) = '__UDF_PLACEHOLDER_107__'
        then 0
        else col281
      end
    ) + (
      0 * coalesce(col282, 0)
    )
  ) as table111,
  (
    (
      case
        when cast(col283 as varchar) = '__UDF_PLACEHOLDER_108__'
        then 0
        else col283
      end
    ) + (
      0 * coalesce(col284, 0)
    )
  ) as table112,
  (
    (
      case
        when cast(col285 as varchar) = '__UDF_PLACEHOLDER_109__'
        then 0
        else col285
      end
    ) + (
      0 * coalesce(col286, 0)
    )
  ) as table113,
  (
    (
      case
        when cast(col287 as varchar) = '__UDF_PLACEHOLDER_110__'
        then 0
        else col287
      end
    ) + (
      0 * coalesce(col288, 0)
    ) + (
      0 * coalesce(col289, 0)
    )
  ) as table114,
  (
    (
      case
        when cast(col290 as varchar) = '__UDF_PLACEHOLDER_111__'
        then 0
        else col290
      end
    ) + (
      0 * coalesce(col291, 0)
    ) + (
      0 * coalesce(col292, 0)
    )
  ) as table115,
  (
    (
      case
        when cast(col95 as varchar) = '__UDF_PLACEHOLDER_112__'
        then 0
        else col95
      end
    ) + (
      0 * coalesce(col109, 0)
    )
  ) as table116,
  (
    (
      case
        when cast(col96 as varchar) = '__UDF_PLACEHOLDER_113__'
        then 0
        else col96
      end
    ) + (
      0 * coalesce(col111, 0)
    )
  ) as table117,
  (
    case
      when cast(col109 as varchar) = '__UDF_PLACEHOLDER_114__'
      then 0
      else col109
    end
  ) as table118,
  (
    case
      when cast(col111 as varchar) = '__UDF_PLACEHOLDER_115__'
      then 0
      else col111
    end
  ) as table119,
  (
    (
      case
        when cast(col95 as varchar) = '__UDF_PLACEHOLDER_116__'
        then 0
        else col95
      end
    ) + (
      0 * coalesce(col293, 0)
    )
  ) as table120,
  (
    (
      case
        when cast(col96 as varchar) = '__UDF_PLACEHOLDER_117__'
        then 0
        else col96
      end
    ) + (
      0 * coalesce(col294, 0)
    )
  ) as table121,
  (
    (
      case
        when cast(col295 as varchar) = '__UDF_PLACEHOLDER_118__'
        then 0
        else col295
      end
    ) + (
      0 * coalesce(col296, 0)
    )
  ) as table122,
  (
    (
      case
        when cast(col297 as varchar) = '__UDF_PLACEHOLDER_119__'
        then 0
        else col297
      end
    ) + (
      0 * coalesce(col298, 0)
    )
  ) as table123,
  (
    (
      case
        when cast(col299 as varchar) = '__UDF_PLACEHOLDER_120__'
        then 0
        else col299
      end
    ) + (
      0 * coalesce(col118, 0)
    ) + (
      0 * coalesce(col117, 0)
    )
  ) as table124,
  (
    (
      case
        when cast(col300 as varchar) = '__UDF_PLACEHOLDER_121__'
        then 0
        else col300
      end
    ) + (
      0 * coalesce(col301, 0)
    )
  ) as table125,
  (
    (
      case
        when cast(col302 as varchar) = '__UDF_PLACEHOLDER_122__'
        then 0
        else col302
      end
    ) + (
      0 * coalesce(col303, 0)
    )
  ) as table126,
  (
    (
      case
        when cast(col304 as varchar) = '__UDF_PLACEHOLDER_123__'
        then 0
        else col304
      end
    ) + (
      0 * coalesce(col305, 0)
    )
  ) as table127,
  (
    (
      case
        when cast(col306 as varchar) = '__UDF_PLACEHOLDER_124__'
        then 0
        else col306
      end
    ) + (
      0 * coalesce(col307, 0)
    )
  ) as table128,
  (
    (
      case
        when cast(col308 as varchar) = '__UDF_PLACEHOLDER_125__'
        then 0
        else col308
      end
    ) + (
      0 * coalesce(col309, 0)
    )
  ) as table129,
  (
    (
      case
        when cast(col310 as varchar) = '__UDF_PLACEHOLDER_126__'
        then 0
        else col310
      end
    ) + (
      0 * coalesce(col309, 0)
    ) + (
      0 * coalesce(col308, 0)
    )
  ) as table130,
  (
    (
      case
        when cast(col311 as varchar) = '__UDF_PLACEHOLDER_127__'
        then 0
        else col311
      end
    ) + (
      0 * coalesce(col312, 0)
    ) + (
      0 * coalesce(col313, 0)
    ) + (
      0 * coalesce(col314, 0)
    )
  ) as table131,
  (
    (
      case
        when cast(col315 as varchar) = '__UDF_PLACEHOLDER_128__'
        then 0
        else col315
      end
    ) + (
      0 * coalesce(col316, 0)
    )
  ) as table132,
  (
    (
      case
        when cast(col317 as varchar) = '__UDF_PLACEHOLDER_129__'
        then 0
        else col317
      end
    ) + (
      0 * coalesce(col316, 0)
    )
  ) as table133,
  (
    (
      case
        when cast(col318 as varchar) = '__UDF_PLACEHOLDER_130__'
        then 0
        else col318
      end
    ) + (
      0 * coalesce(col316, 0)
    )
  ) as table134,
  (
    (
      case
        when cast(col319 as varchar) = '__UDF_PLACEHOLDER_131__'
        then 0
        else col319
      end
    ) + (
      0 * coalesce(col316, 0)
    )
  ) as table135,
  (
    (
      case
        when cast(col320 as varchar) = '__UDF_PLACEHOLDER_132__'
        then 0
        else col320
      end
    ) + (
      0 * coalesce(col316, 0)
    )
  ) as table136,
  (
    (
      case
        when cast(col321 as varchar) = '__UDF_PLACEHOLDER_133__'
        then 0
        else col321
      end
    ) + (
      0 * coalesce(col316, 0)
    )
  ) as table137,
  (
    (
      case
        when cast(col322 as varchar) = '__UDF_PLACEHOLDER_134__'
        then 0
        else col322
      end
    ) + (
      0 * coalesce(col316, 0)
    )
  ) as table138,
  (
    (
      case
        when cast(col323 as varchar) = '__UDF_PLACEHOLDER_135__'
        then 0
        else col323
      end
    ) + (
      0 * coalesce(col316, 0)
    )
  ) as table139,
  (
    (
      case
        when cast(col324 as varchar) = '__UDF_PLACEHOLDER_136__'
        then 0
        else col324
      end
    ) + (
      0 * coalesce(col316, 0)
    )
  ) as table140,
  (
    (
      case
        when cast(col325 as varchar) = '__UDF_PLACEHOLDER_137__'
        then 0
        else col325
      end
    ) + (
      0 * coalesce(col316, 0)
    )
  ) as table141,
  (
    (
      case
        when cast(col326 as varchar) = '__UDF_PLACEHOLDER_138__'
        then 0
        else col326
      end
    ) + (
      0 * coalesce(col316, 0)
    )
  ) as table142,
  (
    (
      case
        when cast(col327 as varchar) = '__UDF_PLACEHOLDER_139__'
        then 0
        else col327
      end
    ) + (
      0 * coalesce(col316, 0)
    )
  ) as table143,
  (
    (
      case
        when cast(col328 as varchar) = '__UDF_PLACEHOLDER_140__'
        then 0
        else col328
      end
    ) + (
      0 * coalesce(col316, 0)
    )
  ) as table144,
  (
    (
      case
        when cast(col329 as varchar) = '__UDF_PLACEHOLDER_141__'
        then 0
        else col329
      end
    ) + (
      0 * coalesce(col316, 0)
    )
  ) as table145,
  (
    (
      case
        when cast(col330 as varchar) = '__UDF_PLACEHOLDER_142__'
        then 0
        else col330
      end
    ) + (
      0 * coalesce(col316, 0)
    )
  ) as table146,
  (
    (
      case
        when cast(col331 as varchar) = '__UDF_PLACEHOLDER_143__'
        then 0
        else col331
      end
    ) + (
      0 * coalesce(col316, 0)
    )
  ) as table147,
  (
    (
      case
        when cast(col332 as varchar) = '__UDF_PLACEHOLDER_144__'
        then 0
        else col332
      end
    ) + (
      0 * coalesce(col316, 0)
    )
  ) as table148,
  (
    (
      case
        when cast(col333 as varchar) = '__UDF_PLACEHOLDER_145__'
        then 0
        else col333
      end
    ) + (
      0 * coalesce(col316, 0)
    )
  ) as table149,
  (
    (
      case
        when cast(col334 as varchar) = '__UDF_PLACEHOLDER_146__'
        then 0
        else col334
      end
    ) + (
      0 * coalesce(col316, 0)
    )
  ) as table150,
  (
    (
      case
        when cast(col335 as varchar) = '__UDF_PLACEHOLDER_147__'
        then 0
        else col335
      end
    ) + (
      0 * coalesce(col316, 0)
    )
  ) as table151,
  (
    (
      case
        when cast(col336 as varchar) = '__UDF_PLACEHOLDER_148__'
        then 0
        else col336
      end
    ) + (
      0 * coalesce(col316, 0)
    )
  ) as table152,
  (
    (
      case
        when cast(col337 as varchar) = '__UDF_PLACEHOLDER_149__'
        then 0
        else col337
      end
    ) + (
      0 * coalesce(col316, 0)
    )
  ) as table153,
  (
    (
      case
        when cast(col338 as varchar) = '__UDF_PLACEHOLDER_150__'
        then 0
        else col338
      end
    ) + (
      0 * coalesce(col316, 0)
    )
  ) as table154,
  (
    (
      case
        when cast(col339 as varchar) = '__UDF_PLACEHOLDER_151__'
        then 0
        else col339
      end
    ) + (
      0 * coalesce(col316, 0)
    )
  ) as table155,
  (
    (
      case
        when cast(col340 as varchar) = '__UDF_PLACEHOLDER_152__'
        then 0
        else col340
      end
    ) + (
      0 * coalesce(col341, 0)
    )
  ) as table156,
  col342,
  col343,
  col344,
  col345,
  col346,
  col347,
  col348,
  col349,
  col350,
  col351,
  col352,
  col353,
  col354,
  col355,
  col356,
  col357,
  col358,
  col359,
  col360,
  col361,
  col362,
  col363,
  col364,
  col365,
  col366,
  col367,
  col368,
  col369,
  col370,
  col371,
  col372,
  col373,
  col374,
  col375,
  col376,
  col377,
  col378,
  col379,
  col380,
  col381,
  col382,
  col383,
  col384,
  col385,
  col386,
  col387,
  col388,
  col389,
  col390,
  col391,
  col392,
  col393,
  col394,
  col395,
  col396,
  col397,
  col398,
  col399,
  col400,
  col401,
  col402,
  col403,
  col404,
  col405,
  col406,
  col407,
  col408,
  col409,
  col410,
  col411,
  col412,
  col413,
  col414,
  col415,
  col300,
  col416,
  col302,
  col417,
  col304,
  (
    (
      case
        when cast(col356 as varchar) = '__UDF_PLACEHOLDER_153__'
        then 0
        else col356
      end
    ) + (
      0 * coalesce(col418, 0)
    ) + (
      0 * coalesce(col342, 0)
    ) + (
      0 * coalesce(col358, 0)
    )
  ) as table157,
  (
    (
      case
        when cast(col356 as varchar) = '__UDF_PLACEHOLDER_154__'
        then 0
        else col356
      end
    ) + (
      0 * coalesce(col418, 0)
    ) + (
      0 * coalesce(col349, 0)
    ) + (
      0 * coalesce(col354, 0)
    )
  ) as table158,
  (
    (
      case
        when cast(col345 as varchar) = '__UDF_PLACEHOLDER_155__'
        then 0
        else col345
      end
    ) + (
      0 * coalesce(col356, 0)
    ) + (
      0 * coalesce(col418, 0)
    ) + (
      0 * coalesce(col358, 0)
    )
  ) as table159,
  (
    (
      case
        when cast(col345 as varchar) = '__UDF_PLACEHOLDER_156__'
        then 0
        else col345
      end
    ) + (
      0 * coalesce(col356, 0)
    ) + (
      0 * coalesce(col418, 0)
    ) + (
      0 * coalesce(col347, 0)
    ) + (
      0 * coalesce(col348, 0)
    )
  ) as table160,
  (
    (
      case
        when cast(col419 as varchar) = '__UDF_PLACEHOLDER_157__'
        then 0
        else col419
      end
    ) + (
      0 * coalesce(col420, 0)
    )
  ) as table161,
  (
    (
      case
        when cast(col421 as varchar) = '__UDF_PLACEHOLDER_158__'
        then 0
        else col421
      end
    ) + (
      0 * coalesce(col422, 0)
    )
  ) as table162,
  col423,
  col424,
  col425,
  col426,
  (
    (
      case
        when cast(col427 as varchar) = '__UDF_PLACEHOLDER_159__'
        then 0
        else col427
      end
    ) + (
      0 * coalesce(col428, 0)
    )
  ) as table163,
  col429 as table164,
  (
    (
      case
        when cast(col429 as varchar) = '__UDF_PLACEHOLDER_160__'
        then 0
        else col429
      end
    ) + (
      0 * coalesce(col427, 0)
    ) + (
      0 * coalesce(col428, 0)
    )
  ) as table165,
  (
    (
      case
        when cast(col430 as varchar) = '__UDF_PLACEHOLDER_161__'
        then 0
        else col430
      end
    ) + (
      0 * coalesce(col431, 0)
    )
  ) as table166,
  col432 as table167,
  (
    (
      case
        when cast(col432 as varchar) = '__UDF_PLACEHOLDER_162__'
        then 0
        else col432
      end
    ) + (
      0 * coalesce(col430, 0)
    ) + (
      0 * coalesce(col431, 0)
    )
  ) as table168,
  (
    (
      case
        when cast(col433 as varchar) = '__UDF_PLACEHOLDER_163__'
        then 0
        else col433
      end
    ) + (
      0 * coalesce(col434, 0)
    ) + (
      0 * coalesce(col435, 0)
    ) + (
      0 * coalesce(col436, 0)
    ) + (
      0 * coalesce(col437, 0)
    ) + (
      0 * coalesce(col438, 0)
    ) + (
      0 * coalesce(col439, 0)
    ) + (
      0 * coalesce(col440, 0)
    ) + (
      0 * coalesce(col441, 0)
    ) + (
      0 * coalesce(col442, 0)
    ) + (
      0 * coalesce(col443, 0)
    ) + (
      0 * coalesce(col444, 0)
    ) + (
      0 * coalesce(col445, 0)
    ) + (
      0 * coalesce(col446, 0)
    ) + (
      0 * coalesce(col447, 0)
    ) + (
      0 * coalesce(col448, 0)
    ) + (
      0 * coalesce(col449, 0)
    )
  ) as table169,
  (
    (
      case
        when cast(col450 as varchar) = '__UDF_PLACEHOLDER_164__'
        then 0
        else col450
      end
    ) + (
      0 * coalesce(col451, 0)
    ) + (
      0 * coalesce(col452, 0)
    ) + (
      0 * coalesce(col453, 0)
    ) + (
      0 * coalesce(col454, 0)
    ) + (
      0 * coalesce(col455, 0)
    ) + (
      0 * coalesce(col456, 0)
    ) + (
      0 * coalesce(col457, 0)
    ) + (
      0 * coalesce(col458, 0)
    ) + (
      0 * coalesce(col459, 0)
    ) + (
      0 * coalesce(col460, 0)
    ) + (
      0 * coalesce(col461, 0)
    ) + (
      0 * coalesce(col462, 0)
    ) + (
      0 * coalesce(col463, 0)
    ) + (
      0 * coalesce(col464, 0)
    ) + (
      0 * coalesce(col465, 0)
    ) + (
      0 * coalesce(col466, 0)
    )
  ) as table170,
  (
    (
      case
        when cast(col434 as varchar) = '__UDF_PLACEHOLDER_165__'
        then 0
        else col434
      end
    ) + (
      0 * coalesce(col436, 0)
    ) + (
      0 * coalesce(col438, 0)
    ) + (
      0 * coalesce(col443, 0)
    ) + (
      0 * coalesce(col444, 0)
    ) + (
      0 * coalesce(col446, 0)
    ) + (
      0 * coalesce(col448, 0)
    ) + (
      0 * coalesce(col449, 0)
    ) + (
      0 * coalesce(col467, 0)
    )
  ) as table171,
  (
    (
      case
        when cast(col451 as varchar) = '__UDF_PLACEHOLDER_166__'
        then 0
        else col451
      end
    ) + (
      0 * coalesce(col453, 0)
    ) + (
      0 * coalesce(col455, 0)
    ) + (
      0 * coalesce(col460, 0)
    ) + (
      0 * coalesce(col461, 0)
    ) + (
      0 * coalesce(col463, 0)
    ) + (
      0 * coalesce(col465, 0)
    ) + (
      0 * coalesce(col466, 0)
    ) + (
      0 * coalesce(col468, 0)
    )
  ) as table172,
  (
    (
      case
        when cast(col469 as varchar) = '__UDF_PLACEHOLDER_167__'
        then 0
        else col469
      end
    ) + (
      0 * coalesce(col470, 0)
    )
  ) as table173,
  (
    (
      case
        when cast(col471 as varchar) = '__UDF_PLACEHOLDER_168__'
        then 0
        else col471
      end
    ) + (
      0 * coalesce(col472, 0)
    )
  ) as table174,
  (
    (
      case
        when cast(col473 as varchar) = '__UDF_PLACEHOLDER_169__'
        then 0
        else col473
      end
    ) + (
      0 * coalesce(col474, 0)
    )
  ) as table175,
  col475,
  (
    (
      case
        when cast(col476 as varchar) = '__UDF_PLACEHOLDER_170__'
        then 0
        else col476
      end
    ) + (
      0 * coalesce(col475, 0)
    )
  ) as table176,
  col477,
  col478,
  (
    (
      case
        when cast(col478 as varchar) = '__UDF_PLACEHOLDER_171__'
        then 0
        else col478
      end
    ) + (
      0 * coalesce(col477, 0)
    )
  ) as table177,
  (
    case
      when cast(col479 as varchar) = '__UDF_PLACEHOLDER_172__'
      then 0
      else col479
    end
  ) as table178,
  (
    case
      when cast(col480 as varchar) = '__UDF_PLACEHOLDER_173__'
      then 0
      else col480
    end
  ) as table179,
  (
    case
      when cast(col481 as varchar) = '__UDF_PLACEHOLDER_174__'
      then 0
      else col481
    end
  ) as table180,
  (
    case
      when cast(col482 as varchar) = '__UDF_PLACEHOLDER_175__'
      then 0
      else col482
    end
  ) as table181,
  (
    (
      case
        when cast(col483 as varchar) = '__UDF_PLACEHOLDER_176__'
        then 0
        else col483
      end
    ) + (
      0 * coalesce(col484, 0)
    )
  ) as table182,
  (
    (
      case
        when cast(col485 as varchar) = '__UDF_PLACEHOLDER_177__'
        then 0
        else col485
      end
    ) + (
      0 * coalesce(col486, 0)
    )
  ) as table183,
  (
    (
      case
        when cast(col487 as varchar) = '__UDF_PLACEHOLDER_178__'
        then 0
        else col487
      end
    ) + (
      0 * coalesce(col488, 0)
    )
  ) as table184,
  (
    (
      case
        when cast(col489 as varchar) = '__UDF_PLACEHOLDER_179__'
        then 0
        else col489
      end
    ) + (
      0 * coalesce(col490, 0)
    )
  ) as table185,
  (
    (
      case
        when cast(col491 as varchar) = '__UDF_PLACEHOLDER_180__'
        then 0
        else col491
      end
    ) + (
      0 * coalesce(col492, 0)
    )
  ) as table186,
  (
    (
      case
        when cast(col493 as varchar) = '__UDF_PLACEHOLDER_181__'
        then 0
        else col493
      end
    ) + (
      0 * coalesce(col494, 0)
    )
  ) as table187,
  (
    (
      case
        when cast(col495 as varchar) = '__UDF_PLACEHOLDER_182__'
        then 0
        else col495
      end
    ) + (
      0 * coalesce(col496, 0)
    )
  ) as table188,
  (
    (
      case
        when cast(col497 as varchar) = '__UDF_PLACEHOLDER_183__'
        then 0
        else col497
      end
    ) + (
      0 * coalesce(col498, 0)
    )
  ) as table189,
  (
    (
      case
        when cast(col499 as varchar) = '__UDF_PLACEHOLDER_184__'
        then 0
        else col499
      end
    ) + (
      0 * coalesce(col500, 0)
    )
  ) as table190,
  (
    (
      case
        when cast(col501 as varchar) = '__UDF_PLACEHOLDER_185__'
        then 0
        else col501
      end
    ) + (
      0 * coalesce(col502, 0)
    )
  ) as table191,
  (
    (
      case
        when cast(col503 as varchar) = '__UDF_PLACEHOLDER_186__'
        then 0
        else col503
      end
    ) + (
      0 * coalesce(col504, 0)
    )
  ) as table192,
  (
    (
      case
        when cast(col505 as varchar) = '__UDF_PLACEHOLDER_187__'
        then 0
        else col505
      end
    ) + (
      0 * coalesce(col506, 0)
    )
  ) as table193,
  (
    (
      case
        when cast(col507 as varchar) = '__UDF_PLACEHOLDER_188__'
        then 0
        else col507
      end
    ) + (
      0 * coalesce(col508, 0)
    )
  ) as table194,
  col469 as table195,
  col471 as table196,
  col473 as table197,
  col509,
  (
    (
      case
        when cast(col510 as varchar) = '__UDF_PLACEHOLDER_189__'
        then 0
        else col510
      end
    ) + (
      0 * coalesce(col509, 0)
    )
  ) as table198,
  (
    (
      case
        when cast(col511 as varchar) = '__UDF_PLACEHOLDER_190__'
        then 0
        else col511
      end
    ) + (
      0 * coalesce(col512, 0)
    ) + (
      0 * coalesce(col513, 0)
    ) + (
      0 * coalesce(col514, 0)
    )
  ) as table199
from (
  select
    col515.col1,
    coalesce(
      AVG(col516.col106),
      AVG(col517.col106),
      AVG(col518.col106),
      AVG(col519.col106),
      AVG(col520.col106)
    ) as table200,
    coalesce(
      max(col516.col3),
      max(col517.col3),
      max(col518.col3),
      max(col519.col3),
      max(col520.col3)
    ) as table201,
    coalesce(
      max(col516.col4),
      max(col517.col4),
      max(col518.col4),
      max(col519.col4),
      max(col520.col4)
    ) as table202,
    coalesce(
      max(col516.col2),
      max(col517.col2),
      max(col518.col2),
      max(col519.col2),
      max(col520.col2)
    ) as table203,
    sum(col150) as table204,
    sum(col351) as table205,
    sum(col316) as table206,
    sum(col324) as table207,
    sum(col86) as table208,
    sum(col366) as table209,
    sum(col290) as table210,
    sum(col269) as table211,
    sum(col362) as table212,
    sum(col343) as table213,
    sum(col152) as table214,
    sum(col89) as table215,
    sum(col274) as table216,
    sum(col347) as table217,
    sum(col158) as table218,
    sum(col278) as table219,
    sum(col264) as table220,
    sum(col159) as table221,
    sum(col289) as table222,
    max(col260) as table223,
    sum(col328) as table224,
    sum(col81) as table225,
    sum(col133) as table226,
    sum(col135) as table227,
    sum(col336) as table228,
    sum(col374) as table229,
    sum(col110) as table230,
    sum(col332) as table231,
    sum(col370) as table232,
    sum(col354) as table233,
    sum(col273) as table234,
    sum(col145) as table235,
    sum(col138) as table236,
    sum(col358) as table237,
    sum(col83) as table238,
    sum(col87) as table239,
    sum(col164) as table240,
    sum(col258) as table241,
    sum(col109) as table242,
    sum(col317) as table243,
    sum(col259) as table244,
    sum(col359) as table245,
    sum(col149) as table246,
    sum(col350) as table247,
    sum(col327) as table248,
    sum(col365) as table249,
    sum(col323) as table250,
    sum(col361) as table251,
    sum(col136) as table252,
    sum(col147) as table253,
    sum(col346) as table254,
    sum(col85) as table255,
    sum(col275) as table256,
    sum(col288) as table257,
    sum(col90) as table258,
    max(col261) as table259,
    sum(col369) as table260,
    sum(col315) as table261,
    sum(col335) as table262,
    sum(col331) as table263,
    sum(col373) as table264,
    sum(col131) as table265,
    sum(col272) as table266,
    sum(col342) as table267,
    sum(col141) as table268,
    sum(col357) as table269,
    sum(col144) as table270,
    sum(col154) as table271,
    sum(col79) as table272,
    sum(col268) as table273,
    sum(col219) as table274,
    sum(col82) as table275,
    sum(col266) as table276,
    sum(col340) as table277,
    sum(col113) as table278,
    sum(col320) as table279,
    sum(col339) as table280,
    sum(col265) as table281,
    sum(col257) as table282,
    sum(col326) as table283,
    sum(col368) as table284,
    sum(col286) as table285,
    sum(col322) as table286,
    sum(col364) as table287,
    sum(col360) as table288,
    sum(col345) as table289,
    sum(col284) as table290,
    sum(col151) as table291,
    sum(col349) as table292,
    sum(col148) as table293,
    sum(col287) as table294,
    sum(col91) as table295,
    sum(col330) as table296,
    sum(col277) as table297,
    sum(col282) as table298,
    sum(col338) as table299,
    sum(col134) as table300,
    sum(col334) as table301,
    sum(col341) as table302,
    sum(col130) as table303,
    sum(col372) as table304,
    sum(col291) as table305,
    sum(col353) as table306,
    sum(col356) as table307,
    sum(col140) as table308,
    sum(col280) as table309,
    sum(col218) as table310,
    sum(col143) as table311,
    sum(col80) as table312,
    sum(col88) as table313,
    sum(col271) as table314,
    sum(col114) as table315,
    sum(col319) as table316,
    sum(col111) as table317,
    sum(col367) as table318,
    sum(col285) as table319,
    sum(col352) as table320,
    sum(col325) as table321,
    sum(col363) as table322,
    sum(col321) as table323,
    sum(col153) as table324,
    sum(col283) as table325,
    sum(col344) as table326,
    sum(col348) as table327,
    sum(col146) as table328,
    sum(col276) as table329,
    sum(col129) as table330,
    sum(col270) as table331,
    sum(col329) as table332,
    sum(col337) as table333,
    sum(col132) as table334,
    sum(col137) as table335,
    sum(col333) as table336,
    sum(col112) as table337,
    AVG(col255) as table338,
    sum(col371) as table339,
    sum(col292) as table340,
    sum(col84) as table341,
    sum(col279) as table342,
    sum(col355) as table343,
    sum(col139) as table344,
    sum(col217) as table345,
    sum(col418) as table346,
    sum(col281) as table347,
    sum(col142) as table348,
    sum(col163) as table349,
    sum(col256) as table350,
    sum(col318) as table351,
    sum(col267) as table352,
    sum(col397) as table353,
    sum(col293) as table354,
    sum(col399) as table355,
    sum(col97) as table356,
    sum(col262) as table357,
    sum(col414) as table358,
    sum(col393) as table359,
    sum(col376) as table360,
    sum(col421) as table361,
    sum(col395) as table362,
    sum(col102) as table363,
    sum(col419) as table364,
    sum(col127) as table365,
    sum(col104) as table366,
    sum(col492) as table367,
    sum(col124) as table368,
    sum(col497) as table369,
    sum(col298) as table370,
    sum(col123) as table371,
    sum(col411) as table372,
    sum(col390) as table373,
    sum(col392) as table374,
    sum(col408) as table375,
    sum(col385) as table376,
    sum(col108) as table377,
    sum(col410) as table378,
    sum(col387) as table379,
    sum(col314) as table380,
    sum(col496) as table381,
    sum(col404) as table382,
    sum(col491) as table383,
    sum(col383) as table384,
    sum(col406) as table385,
    sum(col71) as table386,
    sum(col96) as table387,
    sum(col92) as table388,
    sum(col99) as table389,
    sum(col312) as table390,
    sum(col122) as table391,
    sum(col70) as table392,
    sum(col380) as table393,
    sum(col120) as table394,
    sum(col378) as table395,
    sum(col125) as table396,
    sum(col401) as table397,
    sum(col295) as table398,
    sum(col382) as table399,
    sum(col396) as table400,
    sum(col398) as table401,
    sum(col95) as table402,
    sum(col263) as table403,
    sum(col422) as table404,
    sum(col377) as table405,
    sum(col98) as table406,
    sum(col420) as table407,
    sum(col394) as table408,
    sum(col375) as table409,
    sum(col126) as table410,
    sum(col413) as table411,
    sum(col101) as table412,
    sum(col494) as table413,
    sum(col103) as table414,
    sum(col495) as table415,
    sum(col296) as table416,
    sum(col412) as table417,
    sum(col389) as table418,
    sum(col391) as table419,
    sum(col105) as table420,
    sum(col407) as table421,
    sum(col386) as table422,
    sum(col94) as table423,
    sum(col409) as table424,
    sum(col388) as table425,
    sum(col313) as table426,
    sum(col403) as table427,
    sum(col498) as table428,
    sum(col405) as table429,
    sum(col493) as table430,
    sum(col384) as table431,
    sum(col72) as table432,
    sum(col93) as table433,
    sum(col294) as table434,
    sum(col311) as table435,
    sum(col100) as table436,
    sum(col69) as table437,
    sum(col381) as table438,
    sum(col379) as table439,
    sum(col128) as table440,
    sum(col400) as table441,
    sum(col121) as table442,
    sum(col402) as table443,
    sum(col119) as table444,
    sum(col297) as table445,
    sum(col74) as table446,
    sum(col499) as table447,
    sum(col500) as table448,
    sum(col73) as table449,
    sum(col501) as table450,
    sum(col116) as table451,
    sum(col118) as table452,
    sum(col502) as table453,
    sum(col503) as table454,
    sum(col115) as table455,
    sum(col504) as table456,
    sum(col77) as table457,
    sum(col75) as table458,
    sum(col310) as table459,
    sum(col488) as table460,
    sum(col76) as table461,
    sum(col490) as table462,
    sum(col78) as table463,
    sum(col309) as table464,
    sum(col483) as table465,
    sum(col308) as table466,
    sum(col485) as table467,
    sum(col487) as table468,
    sum(col489) as table469,
    sum(col484) as table470,
    sum(col486) as table471,
    sum(col305) as table472,
    sum(col481) as table473,
    sum(col482) as table474,
    sum(col307) as table475,
    sum(col479) as table476,
    sum(col301) as table477,
    sum(col303) as table478,
    sum(col480) as table479,
    sum(col299) as table480,
    sum(col505) as table481,
    sum(col302) as table482,
    sum(col506) as table483,
    sum(col117) as table484,
    max(col417) as table485,
    max(col416) as table486,
    sum(col300) as table487,
    max(col415) as table488,
    sum(col306) as table489,
    sum(col304) as table490,
    sum(col226) as table491,
    sum(col35) as table492,
    sum(col52) as table493,
    sum(col230) as table494,
    sum(col439) as table495,
    sum(col205) as table496,
    sum(col456) as table497,
    sum(col521) as table498,
    sum(col43) as table499,
    sum(col214) as table500,
    sum(col522) as table501,
    sum(col48) as table502,
    sum(col250) as table503,
    sum(col231) as table504,
    sum(col173) as table505,
    sum(col242) as table506,
    sum(col253) as table507,
    sum(col244) as table508,
    sum(col169) as table509,
    sum(col178) as table510,
    sum(col451) as table511,
    sum(col523) as table512,
    sum(col434) as table513,
    sum(col524) as table514,
    sum(col237) as table515,
    sum(col469) as table516,
    sum(col474) as table517,
    sum(col240) as table518,
    sum(col162) as table519,
    sum(col62) as table520,
    sum(col51) as table521,
    sum(col42) as table522,
    sum(col46) as table523,
    sum(col196) as table524,
    sum(col34) as table525,
    sum(col249) as table526,
    sum(col478) as table527,
    sum(col429) as table528,
    sum(col189) as table529,
    sum(col184) as table530,
    sum(col216) as table531,
    sum(col525) as table532,
    sum(col181) as table533,
    sum(col423) as table534,
    sum(col454) as table535,
    sum(col204) as table536,
    sum(col437) as table537,
    sum(col526) as table538,
    sum(col209) as table539,
    sum(col460) as table540,
    sum(col443) as table541,
    sum(col527) as table542,
    sum(col165) as table543,
    sum(col432) as table544,
    sum(col511) as table545,
    sum(col476) as table546,
    sum(col55) as table547,
    sum(col66) as table548,
    sum(col238) as table549,
    sum(col514) as table550,
    sum(col510) as table551,
    sum(col167) as table552,
    sum(col172) as table553,
    sum(col470) as table554,
    sum(col203) as table555,
    sum(col452) as table556,
    sum(col435) as table557,
    sum(col528) as table558,
    sum(col508) as table559,
    sum(col170) as table560,
    sum(col197) as table561,
    sum(col430) as table562,
    sum(col232) as table563,
    sum(col50) as table564,
    sum(col161) as table565,
    sum(col194) as table566,
    sum(col37) as table567,
    sum(col61) as table568,
    sum(col190) as table569,
    sum(col44) as table570,
    sum(col195) as table571,
    sum(col33) as table572,
    sum(col193) as table573,
    sum(col457) as table574,
    sum(col440) as table575,
    sum(col206) as table576,
    sum(col529) as table577,
    sum(col246) as table578,
    sum(col530) as table579,
    sum(col467) as table580,
    sum(col468) as table581,
    sum(col531) as table582,
    sum(col183) as table583,
    sum(col426) as table584,
    sum(col188) as table585,
    sum(col210) as table586,
    sum(col461) as table587,
    sum(col444) as table588,
    sum(col532) as table589,
    sum(col155) as table590,
    sum(col455) as table591,
    sum(col438) as table592,
    sum(col533) as table593,
    sum(col534) as table594,
    sum(col180) as table595,
    sum(col235) as table596,
    sum(col446) as table597,
    sum(col535) as table598,
    sum(col463) as table599,
    sum(col536) as table600,
    sum(col201) as table601,
    sum(col198) as table602,
    sum(col512) as table603,
    sum(col47) as table604,
    sum(col166) as table605,
    sum(col537) as table606,
    sum(col453) as table607,
    sum(col436) as table608,
    sum(col538) as table609,
    sum(col513) as table610,
    sum(col248) as table611,
    sum(col54) as table612,
    sum(col56) as table613,
    sum(col65) as table614,
    sum(col509) as table615,
    sum(col233) as table616,
    sum(col171) as table617,
    sum(col175) as table618,
    sum(col215) as table619,
    sum(col539) as table620,
    sum(col473) as table621,
    sum(col168) as table622,
    sum(col199) as table623,
    sum(col507) as table624,
    sum(col229) as table625,
    sum(col68) as table626,
    sum(col427) as table627,
    sum(col251) as table628,
    sum(col225) as table629,
    sum(col38) as table630,
    sum(col156) as table631,
    sum(col60) as table632,
    sum(col41) as table633,
    sum(col431) as table634,
    sum(col428) as table635,
    sum(col540) as table636,
    sum(col32) as table637,
    sum(col45) as table638,
    sum(col475) as table639,
    sum(col458) as table640,
    sum(col207) as table641,
    sum(col441) as table642,
    sum(col541) as table643,
    sum(col228) as table644,
    sum(col36) as table645,
    sum(col212) as table646,
    sum(col542) as table647,
    sum(col187) as table648,
    sum(col185) as table649,
    sum(col425) as table650,
    sum(col211) as table651,
    sum(col462) as table652,
    sum(col445) as table653,
    sum(col543) as table654,
    sum(col224) as table655,
    sum(col221) as table656,
    sum(col179) as table657,
    sum(col59) as table658,
    sum(col222) as table659,
    sum(col174) as table660,
    sum(col254) as table661,
    sum(col252) as table662,
    sum(col53) as table663,
    sum(col234) as table664,
    sum(col39) as table665,
    sum(col49) as table666,
    sum(col176) as table667,
    sum(col227) as table668,
    sum(col245) as table669,
    sum(col544) as table670,
    sum(col450) as table671,
    sum(col433) as table672,
    sum(col545) as table673,
    sum(col546) as table674,
    sum(col448) as table675,
    sum(col465) as table676,
    sum(col547) as table677,
    sum(col223) as table678,
    sum(col200) as table679,
    sum(col471) as table680,
    sum(col186) as table681,
    sum(col247) as table682,
    sum(col239) as table683,
    sum(col67) as table684,
    sum(col191) as table685,
    sum(col57) as table686,
    sum(col192) as table687,
    sum(col31) as table688,
    sum(col58) as table689,
    sum(col63) as table690,
    sum(col236) as table691,
    sum(col40) as table692,
    sum(col64) as table693,
    sum(col243) as table694,
    sum(col241) as table695,
    sum(col477) as table696,
    sum(col213) as table697,
    sum(col548) as table698,
    sum(col549) as table699,
    sum(col449) as table700,
    sum(col466) as table701,
    sum(col550) as table702,
    sum(col177) as table703,
    sum(col424) as table704,
    sum(col220) as table705,
    sum(col472) as table706,
    sum(col182) as table707,
    sum(col464) as table708,
    sum(col202) as table709,
    sum(col447) as table710,
    sum(col551) as table711,
    sum(col459) as table712,
    sum(col208) as table713,
    sum(col442) as table714,
    sum(col552) as table715,
    COUNT(*) as table716,
    sum(col517.col107) as table717,
    sum(col518.col157) as table718
  from (
    select
      col1,
      col2,
      col553,
      table4.col9,
      table4.col10
    from (
      select
        table4.col1 as table719,
        table4.col2 as table203,
        table4.col5 as table720,
        table4.col9,
        table4.col10
      from table721 as table4
      inner join table2
        on table4.col1 = table2.col1
        and table4.col5 = table2.col6
        and table4.col9 = table2.col9
        and table4.col10 = table2.col10
        and table4.col2 = table2.col2
      where
        table4.col1 > '2023-10-09 00:00:00'
        and table4.col1 <= '2023-10-16 00:00:00'
        and (
          (
            table4.col1 > '2023-10-09 09:00:00'
            and table4.col1 <= '2023-10-09 13:00:00'
          )
        )
        and (
          table4.col1 > '2023-10-09 09:00:00'
          and table4.col1 <= '2023-10-09 13:00:00'
        )
    ) as table4
    group by
      col1,
      col2,
      col553,
      table4.col9,
      table4.col10
  ) as table722
  left join (
    select
      table4.col1 as table719,
      table4.col4 as table202,
      table4.col2 as table203,
      table4.col3 as table201,
      table4.col3 as table200,
      table2.col6 as table720,
      table2.col9,
      table2.col10,
      col554 as table204,
      col555 as table205,
      col556 as table206,
      col557 as table207,
      col558 as table208,
      col559 as table209,
      col560 as table210,
      col561 as table211,
      col562 as table212,
      col563 as table213,
      col564 as table214,
      col565 as table215,
      col566 as table216,
      col567 as table217,
      col568 as table218,
      col569 as table219,
      col570 as table220,
      col571 as table221,
      col572 as table222,
      col573 as table223,
      col574 as table224,
      col575 as table225,
      col576 as table226,
      col577 as table227,
      col578 as table228,
      col579 as table229,
      col580 as table230,
      col581 as table231,
      col582 as table232,
      col583 as table233,
      col584 as table234,
      col585 as table235,
      col586 as table236,
      col587 as table237,
      col588 as table238,
      col589 as table239,
      col590 as table240,
      col591 as table241,
      col592 as table242,
      col593 as table243,
      col594 as table244,
      col595 as table245,
      col596 as table246,
      col597 as table247,
      col598 as table248,
      col599 as table249,
      col600 as table250,
      col601 as table251,
      col602 as table252,
      col603 as table253,
      col604 as table254,
      col605 as table255,
      col606 as table256,
      col607 as table257,
      col608 as table258,
      col609 as table259,
      col610 as table260,
      col611 as table261,
      col612 as table262,
      col613 as table263,
      col614 as table264,
      col615 as table265,
      col616 as table266,
      col617 as table267,
      col618 as table268,
      col619 as table269,
      col620 as table270,
      col621 as table271,
      col622 as table272,
      col623 as table273,
      col624 as table274,
      col625 as table275,
      col626 as table276,
      col627 as table277,
      col628 as table278,
      col629 as table279,
      col630 as table280,
      col631 as table281,
      col632 as table282,
      col633 as table283,
      col634 as table284,
      col635 as table285,
      col636 as table286,
      col637 as table287,
      col638 as table288,
      col639 as table289,
      col640 as table290,
      col641 as table291,
      col642 as table292,
      col643 as table293,
      col644 as table294,
      col645 as table295,
      col646 as table296,
      col647 as table297,
      col648 as table298,
      col649 as table299,
      col650 as table300,
      col651 as table301,
      col652 as table302,
      col653 as table303,
      col654 as table304,
      col655 as table305,
      col656 as table306,
      col657 as table307,
      col658 as table308,
      col659 as table309,
      col660 as table310,
      col661 as table311,
      col662 as table312,
      col663 as table313,
      col664 as table314,
      col665 as table315,
      col666 as table316,
      col667 as table317,
      col668 as table318,
      col669 as table319,
      col670 as table320,
      col671 as table321,
      col672 as table322,
      col673 as table323,
      col674 as table324,
      col675 as table325,
      col676 as table326,
      col677 as table327,
      col678 as table328,
      col679 as table329,
      col680 as table330,
      col681 as table331,
      col682 as table332,
      col683 as table333,
      col684 as table334,
      col685 as table335,
      col686 as table336,
      col687 as table337,
      col688 as table338,
      col689 as table339,
      col690 as table340,
      col691 as table341,
      col692 as table342,
      col693 as table343,
      col694 as table344,
      col695 as table345,
      col696 as table346,
      col697 as table347,
      col698 as table348,
      col699 as table349,
      col700 as table350,
      col701 as table351,
      col702 as table352
    from table721 as table4
    inner join table2
      on table4.col1 = table2.col1
      and table4.col5 = table2.col6
      and table4.col9 = table2.col9
      and table4.col10 = table2.col10
      and table4.col2 = table2.col2
    where
      table4.col1 > '2023-10-09 00:00:00'
      and table4.col1 <= '2023-10-16 00:00:00'
      and (
        (
          table4.col1 > '2023-10-09 09:00:00'
          and table4.col1 <= '2023-10-09 13:00:00'
        )
      )
      and (
        table4.col1 > '2023-10-09 09:00:00'
        and table4.col1 <= '2023-10-09 13:00:00'
      )
  ) as table723
    on (
      (
        (
          table722.col1 = table723.col1
          and table722.col2 = table723.col2
        )
        and table722.col553 = table723.col553
      )
      and table722.col9 = table723.col9
    )
    and table722.col10 = table723.col10
  left join (
    select
      table4.col1,
      max(table4.col4) as table202,
      max(table4.col2) as table203,
      max(table4.col3) as table201,
      AVG(table4.col3) as table200,
      table1.col6 as table720,
      table1.col9,
      table1.col10,
      COUNT(
        distinct table4.col5 || table4.col11 || table4.col12 || table4.col13
      ) as table718,
      sum(col703) as table491,
      sum(col704) as table492,
      sum(col705) as table493,
      sum(col706) as table494,
      sum(col707) as table499,
      sum(col708) as table502,
      sum(col709) as table503,
      sum(col710) as table504,
      sum(col711) as table505,
      sum(col712) as table506,
      sum(col713) as table507,
      sum(col714) as table508,
      sum(col715) as table509,
      sum(col716) as table510,
      sum(col717) as table515,
      sum(col718) as table516,
      sum(col719) as table517,
      sum(col720) as table518,
      sum(col721) as table519,
      sum(col722) as table520,
      sum(col723) as table521,
      sum(col724) as table522,
      sum(col725) as table523,
      sum(col726) as table524,
      sum(col727) as table525,
      sum(col728) as table526,
      sum(col729) as table527,
      sum(col730) as table528,
      sum(col731) as table529,
      sum(col732) as table530,
      sum(col733) as table533,
      sum(col734) as table534,
      sum(col735) as table543,
      sum(col736) as table544,
      sum(col737) as table545,
      sum(col738) as table546,
      sum(col739) as table547,
      sum(col740) as table548,
      sum(col741) as table549,
      sum(col742) as table550,
      sum(col743) as table551,
      sum(col744) as table552,
      sum(col745) as table553,
      sum(col746) as table554,
      sum(col747) as table559,
      sum(col748) as table560,
      sum(col749) as table561,
      sum(col750) as table562,
      sum(col751) as table563,
      sum(col752) as table564,
      sum(col753) as table565,
      sum(col754) as table566,
      sum(col755) as table567,
      sum(col756) as table568,
      sum(col757) as table569,
      sum(col758) as table570,
      sum(col759) as table571,
      sum(col760) as table572,
      sum(col761) as table573,
      sum(col762) as table578,
      sum(col763) as table583,
      sum(col764) as table584,
      sum(col765) as table585,
      sum(col766) as table590,
      sum(col767) as table595,
      sum(col768) as table596,
      sum(col769) as table601,
      sum(col770) as table602,
      sum(col771) as table603,
      sum(col772) as table604,
      sum(col773) as table605,
      sum(col774) as table610,
      sum(col775) as table611,
      sum(col776) as table612,
      sum(col777) as table613,
      sum(col778) as table614,
      sum(col779) as table615,
      sum(col780) as table616,
      sum(col781) as table617,
      sum(col782) as table618,
      sum(col783) as table621,
      sum(col784) as table622,
      sum(col785) as table623,
      sum(col786) as table624,
      sum(col787) as table625,
      sum(col788) as table626,
      sum(col789) as table627,
      sum(col790) as table628,
      sum(col791) as table629,
      sum(col792) as table630,
      sum(col793) as table631,
      sum(col794) as table632,
      sum(col795) as table633,
      sum(col796) as table637,
      sum(col797) as table638,
      sum(col798) as table639,
      sum(col799) as table644,
      sum(col800) as table645,
      sum(col801) as table648,
      sum(col802) as table649,
      sum(col803) as table650,
      sum(col804) as table655,
      sum(col805) as table656,
      sum(col806) as table657,
      sum(col807) as table658,
      sum(col808) as table659,
      sum(col809) as table660,
      sum(col810) as table661,
      sum(col811) as table662,
      sum(col812) as table663,
      sum(col813) as table664,
      sum(col814) as table665,
      sum(col815) as table666,
      sum(col816) as table667,
      sum(col817) as table668,
      sum(col818) as table669,
      sum(col819) as table678,
      sum(col820) as table679,
      sum(col821) as table680,
      sum(col822) as table681,
      sum(col823) as table682,
      sum(col824) as table683,
      sum(col825) as table684,
      sum(col826) as table685,
      sum(col827) as table686,
      sum(col828) as table687,
      sum(col829) as table688,
      sum(col830) as table689,
      sum(col831) as table690,
      sum(col832) as table691,
      sum(col833) as table692,
      sum(col834) as table693,
      sum(col835) as table694,
      sum(col836) as table695,
      sum(col837) as table696,
      sum(col838) as table703,
      sum(col839) as table704,
      sum(col840) as table705,
      sum(col841) as table706,
      sum(col842) as table707
    from table724 as table4
    inner join table1
      on table4.col1 = table1.col1
      and table4.col5 = table1.col5
      and table4.col11 = table1.col11
      and table4.col12 = table1.col12
      and table4.col2 = table1.col2
    where
      table4.col1 > '2023-10-09 00:00:00'
      and table4.col1 <= '2023-10-16 00:00:00'
      and (
        (
          table4.col1 > '2023-10-09 09:00:00'
          and table4.col1 <= '2023-10-09 13:00:00'
        )
      )
      and (
        table4.col1 > '2023-10-09 09:00:00'
        and table4.col1 <= '2023-10-09 13:00:00'
      )
    group by
      table4.col1,
      col553,
      table1.col9,
      table1.col10
  ) as table725
    on (
      (
        (
          table722.col1 = table725.col1
          and table722.col2 = table725.col2
        )
        and table722.col553 = table725.col553
      )
      and table722.col9 = table725.col9
    )
    and table722.col10 = table725.col10
  left join (
    select
      table4.col1,
      max(table4.col4) as table202,
      max(table4.col2) as table203,
      max(table4.col3) as table201,
      AVG(table4.col3) as table200,
      col553,
      col9,
      col10,
      COUNT(
        distinct table4.col5 || table4.col11 || table4.col12 || table4.col13
      ) as table718,
      sum(col843) as table597,
      sum(col844) as table598,
      sum(col845) as table599,
      sum(col846) as table600,
      sum(col847) as table606,
      sum(col848) as table607,
      sum(col849) as table608,
      sum(col850) as table609,
      sum(col851) as table495,
      sum(col852) as table496,
      sum(col853) as table497,
      sum(col854) as table498,
      sum(col855) as table500,
      sum(col856) as table501,
      sum(col857) as table634,
      sum(col858) as table635,
      sum(col859) as table636,
      sum(col860) as table640,
      sum(col861) as table641,
      sum(col862) as table642,
      sum(col863) as table643,
      sum(col864) as table574,
      sum(col865) as table575,
      sum(col866) as table576,
      sum(col867) as table577,
      sum(col868) as table619,
      sum(col869) as table620,
      sum(col870) as table646,
      sum(col871) as table647,
      sum(col872) as table670,
      sum(col873) as table671,
      sum(col874) as table672,
      sum(col875) as table673,
      sum(col876) as table674,
      sum(col877) as table675,
      sum(col878) as table676,
      sum(col879) as table677,
      sum(col880) as table579,
      sum(col881) as table580,
      sum(col882) as table581,
      sum(col883) as table582,
      sum(col884) as table697,
      sum(col885) as table698,
      sum(col886) as table511,
      sum(col887) as table512,
      sum(col888) as table513,
      sum(col889) as table514,
      sum(col890) as table531,
      sum(col891) as table532,
      sum(col892) as table555,
      sum(col893) as table556,
      sum(col894) as table557,
      sum(col895) as table558,
      sum(col896) as table699,
      sum(col897) as table700,
      sum(col898) as table701,
      sum(col899) as table702,
      sum(col900) as table651,
      sum(col901) as table652,
      sum(col902) as table653,
      sum(col903) as table654,
      sum(col904) as table586,
      sum(col905) as table587,
      sum(col906) as table588,
      sum(col907) as table589,
      sum(col908) as table535,
      sum(col909) as table536,
      sum(col910) as table537,
      sum(col911) as table538,
      sum(col912) as table539,
      sum(col913) as table540,
      sum(col914) as table541,
      sum(col915) as table542,
      sum(col916) as table591,
      sum(col917) as table592,
      sum(col918) as table593,
      sum(col919) as table594,
      sum(col920) as table708,
      sum(col921) as table709,
      sum(col922) as table710,
      sum(col923) as table711,
      sum(col924) as table712,
      sum(col925) as table713,
      sum(col926) as table714,
      sum(col927) as table715
    from (
      select
        table4.col1 as table719,
        table4.col14 as table726,
        table4.col4 as table202,
        table4.col2 as table203,
        max(table4.col3) as table201,
        table4.col5,
        table4.col11,
        table4.col12,
        table4.col13,
        table1.col6 as table720,
        table1.col9,
        table1.col10,
        max(table4.col15) as table727,
        max(table4.col16) as table728,
        max(table4.col17) as table729,
        max(table4.col18) as table730,
        max(table4.col19) as table731,
        max(table4.col20) as table732,
        max(table4.col21) as table733,
        max(table4.col22) as table734,
        max(table4.col23) as table735,
        max(case col928 when '1' then col846 else null end) as table736,
        sum(col846) as table737,
        max(case col928 when '5' then col846 else null end) as table738,
        sum(col846) as table739,
        sum(col850) as table740,
        max(case col928 when '5' then col850 else null end) as table741,
        max(case col928 when '1' then col850 else null end) as table742,
        sum(col850) as table743,
        max(case col928 when '1' then col854 else null end) as table744,
        sum(col854) as table745,
        max(case col928 when '5' then col854 else null end) as table746,
        sum(col854) as table747,
        sum(col856) as table748,
        sum(col856) as table749,
        sum(col869) as table750,
        sum(col869) as table751,
        sum(col875) as table752,
        max(case col928 when '5' then col875 else null end) as table753,
        max(case col928 when '1' then col875 else null end) as table754,
        sum(col875) as table755,
        sum(col879) as table756,
        max(case col928 when '1' then col879 else null end) as table757,
        max(case col928 when '5' then col879 else null end) as table758,
        sum(col879) as table759,
        max(case col928 when '5' then col889 else null end) as table760,
        sum(col889) as table761,
        max(case col928 when '1' then col889 else null end) as table762,
        sum(col889) as table763,
        sum(col895) as table764,
        max(case col928 when '5' then col895 else null end) as table765,
        max(case col928 when '1' then col895 else null end) as table766,
        sum(col895) as table767,
        max(case col928 when '2' then col859 else null end) as table768,
        max(case col928 when '1' then col859 else null end) as table769,
        sum(col859) as table770,
        max(case col928 when '5' then col863 else null end) as table771,
        sum(col863) as table772,
        max(case col928 when '1' then col863 else null end) as table773,
        sum(col863) as table774,
        max(case col928 when '5' then col867 else null end) as table775,
        max(case col928 when '1' then col867 else null end) as table776,
        sum(col867) as table777,
        sum(col867) as table778,
        sum(col871) as table779,
        sum(col871) as table780,
        sum(col883) as table781,
        max(case col928 when '1' then col883 else null end) as table782,
        max(case col928 when '5' then col883 else null end) as table783,
        sum(col883) as table784,
        sum(col885) as table785,
        sum(col885) as table786,
        sum(col891) as table787,
        sum(col891) as table788,
        sum(col899) as table789,
        max(case col928 when '1' then col899 else null end) as table790,
        max(case col928 when '5' then col899 else null end) as table791,
        sum(col899) as table792,
        sum(col903) as table793,
        max(case col928 when '5' then col903 else null end) as table794,
        max(case col928 when '1' then col903 else null end) as table795,
        sum(col903) as table796,
        sum(col907) as table797,
        max(case col928 when '5' then col907 else null end) as table798,
        max(case col928 when '1' then col907 else null end) as table799,
        sum(col907) as table800,
        max(case col928 when '5' then col911 else null end) as table801,
        sum(col911) as table802,
        max(case col928 when '1' then col911 else null end) as table803,
        sum(col911) as table804,
        sum(col915) as table805,
        max(case col928 when '5' then col915 else null end) as table806,
        max(case col928 when '1' then col915 else null end) as table807,
        sum(col915) as table808,
        max(case col928 when '5' then col919 else null end) as table809,
        max(case col928 when '1' then col919 else null end) as table810,
        sum(col919) as table811,
        sum(col919) as table812,
        max(case col928 when '5' then col923 else null end) as table813,
        sum(col923) as table814,
        max(case col928 when '1' then col923 else null end) as table815,
        sum(col923) as table816,
        max(case col928 when '5' then col927 else null end) as table817,
        sum(col927) as table818,
        max(case col928 when '1' then col927 else null end) as table819,
        sum(col927) as table820
      from table821 as table4
      inner join table1
        on table4.col1 = table1.col1
        and table4.col5 = table1.col5
        and table4.col11 = table1.col11
        and table4.col12 = table1.col12
        and table4.col2 = table1.col2
      where
        table4.col1 > '2023-10-09 00:00:00'
        and table4.col1 <= '2023-10-16 00:00:00'
        and (
          (
            table4.col1 > '2023-10-09 09:00:00'
            and table4.col1 <= '2023-10-09 13:00:00'
          )
        )
        and (
          table4.col1 > '2023-10-09 09:00:00'
          and table4.col1 <= '2023-10-09 13:00:00'
        )
      group by
        table4.col1,
        table4.col14,
        table4.col4,
        table4.col2,
        table4.col5,
        table4.col11,
        table4.col12,
        table4.col13,
        col553,
        table1.col9,
        table1.col10
    ) as table4
    group by
      table4.col1,
      col553,
      col9,
      col10
  ) as table822
    on (
      (
        (
          table722.col1 = table822.col1
          and table722.col2 = table822.col2
        )
        and table722.col553 = table822.col553
      )
      and table722.col9 = table822.col9
    )
    and table722.col10 = table822.col10
  left join (
    select
      table4.col1,
      max(table4.col4) as table202,
      max(table4.col2) as table203,
      max(table4.col3) as table201,
      AVG(table4.col3) as table200,
      table1.col6 as table720,
      table1.col9,
      table1.col10,
      sum(col929) as table446,
      sum(col930) as table447,
      sum(col931) as table448,
      sum(col932) as table449,
      sum(col933) as table450,
      sum(col934) as table451,
      sum(col935) as table452,
      sum(col936) as table453,
      sum(col937) as table454,
      sum(col938) as table455,
      sum(col939) as table456,
      sum(col940) as table457,
      sum(col941) as table458,
      sum(col942) as table459,
      sum(col943) as table460,
      sum(col944) as table461,
      sum(col945) as table462,
      sum(col946) as table463,
      sum(col947) as table464,
      sum(col948) as table465,
      sum(col949) as table466,
      sum(col950) as table467,
      sum(col951) as table468,
      sum(col952) as table469,
      sum(col953) as table470,
      sum(col954) as table471,
      sum(col955) as table472,
      sum(col956) as table473,
      sum(col957) as table474,
      sum(col958) as table475,
      sum(col959) as table476,
      sum(col960) as table477,
      sum(col961) as table478,
      sum(col962) as table479,
      sum(col963) as table480,
      sum(col964) as table481,
      sum(col965) as table482,
      sum(col966) as table483,
      sum(col967) as table484,
      max(col968) as table485,
      max(col969) as table486,
      sum(col970) as table487,
      max(col971) as table488,
      sum(col972) as table489,
      sum(col973) as table490
    from table823 as table4
    inner join table1
      on table4.col1 = table1.col1
      and table4.col5 = table1.col5
      and table4.col11 = table1.col11
      and table4.col12 = table1.col12
      and table4.col2 = table1.col2
    where
      table4.col1 > '2023-10-09 00:00:00'
      and table4.col1 <= '2023-10-16 00:00:00'
      and (
        (
          table4.col1 > '2023-10-09 09:00:00'
          and table4.col1 <= '2023-10-09 13:00:00'
        )
      )
      and (
        table4.col1 > '2023-10-09 09:00:00'
        and table4.col1 <= '2023-10-09 13:00:00'
      )
    group by
      table4.col1,
      col553,
      table1.col9,
      table1.col10
  ) as table824
    on (
      (
        (
          table722.col1 = table824.col1
          and table722.col2 = table824.col2
        )
        and table722.col553 = table824.col553
      )
      and table722.col9 = table824.col9
    )
    and table722.col10 = table824.col10
  left join (
    select
      table4.col1,
      max(table4.col4) as table202,
      max(table4.col2) as table203,
      max(table4.col3) as table201,
      AVG(table4.col3) as table200,
      table1.col6 as table720,
      table1.col9,
      table1.col10,
      COUNT(
        distinct table4.col5 || table4.col24 || table4.col25 || table4.col26
      ) as table717,
      sum(col974) as table353,
      sum(col975) as table354,
      sum(col976) as table355,
      sum(col977) as table356,
      sum(col978) as table357,
      sum(col979) as table358,
      sum(col980) as table359,
      sum(col981) as table360,
      sum(col982) as table361,
      sum(col983) as table362,
      sum(col984) as table363,
      sum(col985) as table364,
      sum(col986) as table365,
      sum(col987) as table366,
      sum(col988) as table367,
      sum(col989) as table368,
      sum(col990) as table369,
      sum(col991) as table370,
      sum(col992) as table371,
      sum(col993) as table372,
      sum(col994) as table373,
      sum(col995) as table374,
      sum(col996) as table375,
      sum(col997) as table376,
      sum(col998) as table377,
      sum(col999) as table378,
      sum(col1000) as table379,
      sum(col1001) as table380,
      sum(col1002) as table381,
      sum(col1003) as table382,
      sum(col1004) as table383,
      sum(col1005) as table384,
      sum(col1006) as table385,
      sum(col1007) as table386,
      sum(col1008) as table387,
      sum(col1009) as table388,
      sum(col1010) as table389,
      sum(col1011) as table390,
      sum(col1012) as table391,
      sum(col1013) as table392,
      sum(col1014) as table393,
      sum(col1015) as table394,
      sum(col1016) as table395,
      sum(col1017) as table396,
      sum(col1018) as table397,
      sum(col1019) as table398,
      sum(col1020) as table399,
      sum(col1021) as table400,
      sum(col1022) as table401,
      sum(col1023) as table402,
      sum(col1024) as table403,
      sum(col1025) as table404,
      sum(col1026) as table405,
      sum(col1027) as table406,
      sum(col1028) as table407,
      sum(col1029) as table408,
      sum(col1030) as table409,
      sum(col1031) as table410,
      sum(col1032) as table411,
      sum(col1033) as table412,
      sum(col1034) as table413,
      sum(col1035) as table414,
      sum(col1036) as table415,
      sum(col1037) as table416,
      sum(col1038) as table417,
      sum(col1039) as table418,
      sum(col1040) as table419,
      sum(col1041) as table420,
      sum(col1042) as table421,
      sum(col1043) as table422,
      sum(col1044) as table423,
      sum(col1045) as table424,
      sum(col1046) as table425,
      sum(col1047) as table426,
      sum(col1048) as table427,
      sum(col1049) as table428,
      sum(col1050) as table429,
      sum(col1051) as table430,
      sum(col1052) as table431,
      sum(col1053) as table432,
      sum(col1054) as table433,
      sum(col1055) as table434,
      sum(col1056) as table435,
      sum(col1057) as table436,
      sum(col1058) as table437,
      sum(col1059) as table438,
      sum(col1060) as table439,
      sum(col1061) as table440,
      sum(col1062) as table441,
      sum(col1063) as table442,
      sum(col1064) as table443,
      sum(col1065) as table444,
      sum(col1066) as table445
    from table825 as table4
    inner join table1
      on table4.col1 = table1.col1
      and table4.col5 = table1.col6
      and table4.col24 = table1.col24
      and table4.col25 = table1.col25
      and table4.col2 = table1.col2
    where
      table4.col1 > '2023-10-09 00:00:00'
      and table4.col1 <= '2023-10-16 00:00:00'
      and (
        (
          table4.col1 > '2023-10-09 09:00:00'
          and table4.col1 <= '2023-10-09 13:00:00'
        )
      )
      and (
        table4.col1 > '2023-10-09 09:00:00'
        and table4.col1 <= '2023-10-09 13:00:00'
      )
    group by
      table4.col1,
      col553,
      table1.col9,
      table1.col10
  ) as table826
    on (
      (
        (
          table722.col1 = table826.col1
          and table722.col2 = table826.col2
        )
        and table722.col553 = table826.col553
      )
      and table722.col9 = table826.col9
    )
    and table722.col10 = table826.col10
  group by
    table722.col1,
    table722.col2
) as table6
order by
  col1067,
  col1068,
  col2
limit 16778
col1069 0