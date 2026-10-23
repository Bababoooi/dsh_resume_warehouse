# AC 覆盖账本（自动生成，勿手改）

- 条款总数（分母）：**160**
- 已执行（断言）：**157**
- 人工验（MANUAL）：**3**
- 未覆盖：**0**

重新生成：`.venv/bin/python tests/acceptance/make_index.py`　自校验：`.venv/bin/python tests/acceptance/make_index.py --check`

## 按分组

| 分组 | 条款 | 已执行 | MANUAL | 覆盖率 |
| --- | --- | --- | --- | --- |
| ANL | 12 | 12 | 0 | 100% |
| BUILD | 12 | 12 | 0 | 100% |
| CONFLICT | 2 | 2 | 0 | 100% |
| EN | 4 | 4 | 0 | 100% |
| ENV | 11 | 11 | 0 | 100% |
| FETCH | 3 | 3 | 0 | 100% |
| FILE | 1 | 1 | 0 | 100% |
| IMPORT | 21 | 21 | 0 | 100% |
| JD | 5 | 4 | 1 | 80% |
| LLM | 12 | 12 | 0 | 100% |
| LOC | 7 | 6 | 1 | 85% |
| NAME | 9 | 9 | 0 | 100% |
| PDF | 20 | 19 | 1 | 95% |
| PHOTO | 5 | 5 | 0 | 100% |
| PKG | 1 | 1 | 0 | 100% |
| PRIV | 14 | 14 | 0 | 100% |
| PROF | 2 | 2 | 0 | 100% |
| ROB | 6 | 6 | 0 | 100% |
| SKILL | 4 | 4 | 0 | 100% |
| UI | 9 | 9 | 0 | 100% |

## 逐条明细

| AC ID | 优先级 | 状态 | 执行位置 / 原因 |
| --- | --- | --- | --- |
| AC-ENV-01 | P0 | 已执行 | `test_ac_platform.py::_env_01` |
| AC-ENV-02 | P0 | 已执行 | `test_ac_platform.py::_env_02` |
| AC-ENV-03 | P0 | 已执行 | `test_ac_platform.py::_env_03` |
| AC-ENV-04 | P0 | 已执行 | `test_ac_platform.py::_env_04` |
| AC-ENV-05 | P1 | 已执行 | `test_ac_platform.py::_env_05` |
| AC-ENV-06 | P0 | 已执行 | `test_ac_platform.py::_env_06` |
| AC-ENV-07 | P0 | 已执行 | `test_ac_platform.py::_env_07` |
| AC-ENV-08 | P1 | 已执行 | `test_ac_platform.py::_env_08` |
| AC-ENV-10 | P0 | 已执行 | `test_ac_platform.py::_env_10` |
| AC-ENV-11 | P0 | 已执行 | `test_ac_platform.py::_env_11` |
| AC-ENV-09 | P0 | 已执行 | `test_ac_platform.py::_env_09` |
| AC-LOC-01 | P0 | 已执行 | `test_ac_guards.py::_loc_01` |
| AC-LOC-02 | P0 | 已执行 | `test_ac_platform.py::_loc_02` |
| AC-LOC-03 | P0 | 已执行 | `test_ac_platform.py::_loc_03` |
| AC-LOC-04 | P1 | 已执行 | `test_ac_platform.py::_loc_04` |
| AC-LOC-05 | P0 | 已执行 | `test_ac_platform.py::_loc_05` |
| AC-LOC-06 | P1 | 已执行 | `test_ac_platform.py::_loc_06` |
| AC-LOC-07 | P2 | MANUAL | 需要真实点一次「清空数据」并在输入框里手打 DELETE，再重启服务确认 schema 自动重建。自动化会在真库上删数据，不能跑；请在 data/ 备份后手动验证，命令：`cp -r data data.bak && .venv/bin/python scripts/preflight.py`（重启后查 /api/v1/health 的 db.schema_version）。 |
| AC-PRIV-01 | P0 | 已执行 | `test_ac_platform.py::_priv_01` |
| AC-PRIV-02 | P0 | 已执行 | `test_ac_platform.py::_priv_02` |
| AC-PRIV-03 | P0 | 已执行 | `test_ac_platform.py::_priv_03` |
| AC-PRIV-04 | P0 | 已执行 | `test_ac_platform.py::_priv_04` |
| AC-PRIV-05 | P0 | 已执行 | `test_ac_platform.py::_priv_05` |
| AC-PRIV-06 | P0 | 已执行 | `test_ac_platform.py::_priv_06` |
| AC-PRIV-07 | P0 | 已执行 | `test_ac_platform.py::_priv_07` |
| AC-PRIV-08 | P1 | 已执行 | `test_ac_platform.py::_priv_08` |
| AC-PRIV-09 | P1 | 已执行 | `test_ac_platform.py::_priv_09` |
| AC-PRIV-10 | P0 | 已执行 | `test_ac_platform.py::_priv_10` |
| AC-PRIV-11 | P0 | 已执行 | `test_ac_platform.py::_priv_11` |
| AC-PRIV-13 | P0 | 已执行 | `test_ac_platform.py::_priv_13` |
| AC-PRIV-12 | P0 | 已执行 | `test_ac_platform.py::_priv_12` |
| AC-NAME-01 | P0 | 已执行 | `test_ac_platform.py::_name_01` |
| AC-NAME-02 | P0 | 已执行 | `test_ac_platform.py::_name_02` |
| AC-NAME-03 | P0 | 已执行 | `test_ac_platform.py::_name_03` |
| AC-NAME-04 | P0 | 已执行 | `test_ac_platform.py::_name_04` |
| AC-NAME-05 | P1 | 已执行 | `test_ac_platform.py::_name_05` |
| AC-NAME-06 | P1 | 已执行 | `test_ac_platform.py::_name_06` |
| AC-NAME-07 | P1 | 已执行 | `test_ac_platform.py::_name_07` |
| AC-NAME-08 | P1 | 已执行 | `test_ac_platform.py::_name_08` |
| AC-IMPORT-01 | P0 | 已执行 | `test_ac_import_output.py::_imp_01` |
| AC-IMPORT-02 | P0 | 已执行 | `test_ac_import_output.py::_imp_02` |
| AC-IMPORT-03 | P0 | 已执行 | `test_ac_import_output.py::_imp_03` |
| AC-IMPORT-04 | P1 | 已执行 | `test_ac_import_output.py::_imp_04` |
| AC-IMPORT-05 | P0 | 已执行 | `test_ac_import_output.py::_imp_05` |
| AC-IMPORT-06 | P1 | 已执行 | `test_ac_import_output.py::_imp_06` |
| AC-IMPORT-07 | P0 | 已执行 | `test_ac_import_output.py::_imp_07` |
| AC-IMPORT-08 | P1 | 已执行 | `test_ac_import_output.py::_imp_08` |
| AC-IMPORT-09 | P1 | 已执行 | `test_ac_import_output.py::_imp_09` |
| AC-IMPORT-11 | P0 | 已执行 | `test_ac_import_output.py::_imp_11` |
| AC-IMPORT-12 | P0 | 已执行 | `test_ac_import_output.py::_imp_12` |
| AC-IMPORT-14 | P0 | 已执行 | `test_ac_import_output.py::_imp_14` |
| AC-IMPORT-13 | P1 | 已执行 | `test_ac_guards.py::_import_13` |
| AC-IMPORT-15 | P0 | 已执行 | `test_ac_contract.py::_import_15` |
| AC-IMPORT-16 | P0 | 已执行 | `test_ac_contract.py::_import_16` |
| AC-PKG-14 | P1 | 已执行 | `test_ac_contract.py::_pkg_14` |
| AC-IMPORT-17 | P0 | 已执行 | `test_ac_contract.py::_import_17` |
| AC-IMPORT-18 | P0 | 已执行 | `test_ac_contract.py::_import_18` |
| AC-IMPORT-19 | P0 | 已执行 | `test_ac_contract.py::_import_19` |
| AC-IMPORT-20 | P0 | 已执行 | `test_ac_contract.py::_import_20` |
| AC-IMPORT-21 | P0 | 已执行 | `test_ac_contract.py::_import_21` |
| AC-BUILD-16 | P0 | 已执行 | `test_ac_contract.py::_build_16` |
| AC-CONFLICT-01 | P0 | 已执行 | `test_ac_contract.py::_conflict_01` |
| AC-CONFLICT-02 | P0 | 已执行 | `test_ac_zhpref.py::test_ac_conflict_02_resolved_is_info_and_value_unchanged` |
| AC-PROF-01 | P0 | 已执行 | `test_ac_zhpref.py::test_ac_prof_01_roundtrip_snapshot_and_clear` |
| AC-PROF-02 | P0 | 已执行 | `test_ac_zhpref.py::test_ac_prof_02_available_note_reaches_both_languages` |
| AC-NAME-09 | P1 | 已执行 | `test_ac_contract.py::_name_09` |
| AC-EN-01 | P0 | 已执行 | `test_ac_contract.py::_en_01` |
| AC-EN-02 | P0 | 已执行 | `test_ac_contract.py::_en_02` |
| AC-EN-03 | P1 | 已执行 | `test_ac_contract.py::_en_03` |
| AC-PDF-16 | P0 | 已执行 | `test_ac_contract.py::_pdf_16` |
| AC-PDF-17 | P0 | 已执行 | `test_ac_contract.py::_pdf_17` |
| AC-EN-04 | P0 | 已执行 | `test_ac_contract.py::_en_04` |
| AC-BUILD-15 | P1 | 已执行 | `test_ac_contract.py::_build_15` |
| AC-IMPORT-10 | P2 | 已执行 | `test_ac_guards.py::_import_10` |
| AC-PDF-01 | P0 | 已执行 | `test_ac_import_output.py::_pdf_01` |
| AC-PDF-02 | P0 | 已执行 | `test_ac_import_output.py::_pdf_02` |
| AC-PDF-03 | P0 | 已执行 | `test_ac_import_output.py::_pdf_03` |
| AC-PDF-04 | P0 | 已执行 | `test_ac_import_output.py::_pdf_04` |
| AC-PDF-05 | P0 | 已执行 | `test_ac_import_output.py::_pdf_05` |
| AC-PDF-06 | P0 | 已执行 | `test_ac_import_output.py::_pdf_06` |
| AC-PDF-07 | P1 | 已执行 | `test_ac_import_output.py::_pdf_07` |
| AC-PDF-08 | P0 | 已执行 | `test_ac_import_output.py::_pdf_08` |
| AC-PDF-09 | P1 | 已执行 | `test_ac_import_output.py::_pdf_09` |
| AC-PDF-10 | P1 | 已执行 | `test_ac_import_output.py::_pdf_10` |
| AC-PDF-11 | P0 | 已执行 | `test_ac_import_output.py::_pdf_11` |
| AC-PDF-12 | P0 | 已执行 | `test_ac_import_output.py::_pdf_12` |
| AC-PDF-13 | P1 | 已执行 | `test_ac_guards.py::_pdf_13` |
| AC-PDF-14 | P1 | 已执行 | `test_ac_guards.py::_pdf_14` |
| AC-PDF-15 | P0 | 已执行 | `test_ac_guards.py::_pdf_15` |
| AC-PDF-18 | P0 | 已执行 | `test_ac_contract.py::_pdf_18` |
| AC-PHOTO-01 | P0 | 已执行 | `test_ac_import_output.py::_photo_01` |
| AC-PHOTO-02 | P0 | 已执行 | `test_ac_import_output.py::_photo_02` |
| AC-PHOTO-03 | P0 | 已执行 | `test_ac_import_output.py::_photo_03` |
| AC-PHOTO-05 | P0 | 已执行 | `test_ac_import_output.py::_photo_05` |
| AC-PHOTO-04 | P0 | 已执行 | `test_ac_import_output.py::_photo_04` |
| AC-FILE-01 | P1 | 已执行 | `test_ac_guards.py::_file_01` |
| AC-PDF-19 | P1 | 已执行 | `test_ac_contract.py::_pdf_19` |
| AC-PDF-20 | P2 | MANUAL | 打印版式一致性只能在浏览器打印预览里看：Chrome 打开预览页 → ⌘P → 选 A4、边距选「默认」→ 对比导出的 PDF 首页边距（左右 42.5pt / 上下 45.35pt）。 |
| AC-BUILD-01 | P0 | 已执行 | `test_ac_import_output.py::_build_01` |
| AC-BUILD-02 | P0 | 已执行 | `test_ac_import_output.py::_build_02` |
| AC-BUILD-03 | P0 | 已执行 | `test_ac_import_output.py::_build_03` |
| AC-BUILD-12 | P0 | 已执行 | `test_ac_import_output.py::_build_12` |
| AC-BUILD-13 | P0 | 已执行 | `test_ac_import_output.py::_build_13` |
| AC-BUILD-04 | P1 | 已执行 | `test_ac_guards.py::_build_04` |
| AC-BUILD-05 | P1 | 已执行 | `test_ac_import_output.py::_build_05` |
| AC-BUILD-06 | P1 | 已执行 | `test_ac_guards.py::_build_06` |
| AC-BUILD-07 | P1 | 已执行 | `test_ac_guards.py::_build_07` |
| AC-SKILL-01 | P0 | 已执行 | `test_ac_contract.py::_skill_01` |
| AC-SKILL-02 | P0 | 已执行 | `test_ac_contract.py::_skill_02` |
| AC-SKILL-03 | P1 | 已执行 | `test_ac_contract.py::_skill_03` |
| AC-SKILL-04 | P1 | 已执行 | `test_ac_contract.py::_skill_04` |
| AC-BUILD-08 | P2 | 已执行 | `test_ac_guards.py::_build_08` |
| AC-JD-01 | P0 | 已执行 | `test_ac_import_output.py::_jd_01` |
| AC-JD-02 | P0 | 已执行 | `test_ac_import_output.py::_jd_02` |
| AC-JD-03 | P1 | 已执行 | `test_ac_import_output.py::_jd_03` |
| AC-JD-04 | P1 | 已执行 | `test_ac_guards.py::_jd_04` |
| AC-JD-05 | P2 | MANUAL | CompanyProfile 的手填/LLM 建议属于交互流程：需要人在 #/jobs 页填一次 culture_tags/hiring_signals/source_urls，再点「让 AI 建议」看是否合并进同一份档案（接口侧已有 PATCH/analyze 自动断言兜底）。 |
| AC-FETCH-01 | P0 | 已执行 | `test_ac_guards.py::_fetch_01` |
| AC-FETCH-02 | P0 | 已执行 | `test_ac_guards.py::_fetch_02` |
| AC-FETCH-03 | P0 | 已执行 | `test_ac_guards.py::_fetch_03` |
| AC-ANL-06 | P0 | 已执行 | `test_ac_contract.py::_anl_06` |
| AC-ANL-07 | P0 | 已执行 | `test_ac_contract.py::_anl_07` |
| AC-ANL-09 | P0 | 已执行 | `test_ac_contract.py::_anl_09` |
| AC-ANL-10 | P1 | 已执行 | `test_ac_contract.py::_anl_10` |
| AC-ANL-11 | P0 | 已执行 | `test_ac_contract.py::_anl_11` |
| AC-ANL-12 | P0 | 已执行 | `test_ac_contract.py::_anl_12` |
| AC-ANL-13 | P0 | 已执行 | `test_ac_contract.py::_anl_13` |
| AC-ANL-14 | P0 | 已执行 | `test_ac_contract.py::_anl_14` |
| AC-ANL-15 | P0 | 已执行 | `test_ac_contract.py::_anl_15` |
| AC-ANL-16 | P0 | 已执行 | `test_ac_anl_evidence.py::test_ac_anl_16_matched_evidence_is_traceable` |
| AC-ANL-17 | P0 | 已执行 | `test_ac_anl_evidence.py::test_ac_anl_17_missing_only_when_both_arrays_empty` |
| AC-ANL-18 | P0 | 已执行 | `test_ac_anl_evidence.py::test_ac_anl_18_manual_override_survives_recompute` |
| AC-PRIV-14 | P0 | 已执行 | `test_ac_contract.py::_priv_14` |
| AC-LLM-01 | P0 | 已执行 | `test_ac_guards.py::_llm_01` |
| AC-LLM-02 | P0 | 已执行 | `test_ac_guards.py::_llm_02` |
| AC-LLM-03 | P0 | 已执行 | `test_ac_guards.py::_llm_03` |
| AC-LLM-04 | P1 | 已执行 | `test_ac_guards.py::_llm_04` |
| AC-LLM-05 | P0 | 已执行 | `test_ac_guards.py::_llm_05` |
| AC-LLM-06 | P1 | 已执行 | `test_ac_guards.py::_llm_06` |
| AC-LLM-07 | P2 | 已执行 | `test_ac_guards.py::_llm_07` |
| AC-LLM-08 | P0 | 已执行 | `test_ac_guards.py::_llm_08` |
| AC-LLM-09 | P0 | 已执行 | `test_ac_guards.py::_llm_09` |
| AC-LLM-10 | P0 | 已执行 | `test_ac_guards.py::_llm_10` |
| AC-LLM-11 | P0 | 已执行 | `test_ac_guards.py::_llm_11` |
| AC-LLM-12 | P0 | 已执行 | `test_ac_guards.py::_llm_12` |
| AC-UI-01 | P0 | 已执行 | `test_ac_import_output.py::_ui_01` |
| AC-UI-02 | P0 | 已执行 | `test_ac_import_output.py::_ui_02` |
| AC-UI-03 | P0 | 已执行 | `test_ac_contract.py::_ui_03` |
| AC-UI-04 | P0 | 已执行 | `test_ac_guards.py::_ui_04` |
| AC-UI-05 | P1 | 已执行 | `test_ac_ui_browser.py::test_ac_ui_05_naming_error_links_to_profile` |
| AC-UI-06 | P1 | 已执行 | `test_ac_ui_browser.py::test_ac_ui_06_interrupted_job_shows_chinese_notice` |
| AC-UI-07 | P1 | 已执行 | `test_ac_ui_browser.py::test_ac_ui_07_no_horizontal_scroll_at_1280` |
| AC-UI-08 | P1 | 已执行 | `test_ac_ui_browser.py::test_ac_ui_08_degraded_font_shows_banner_and_disables_export` |
| AC-UI-09 | P1 | 已执行 | `test_ac_ui_browser.py::test_ac_ui_09_error_codes_render_chinese_next_steps` |
| AC-ROB-01 | P0 | 已执行 | `test_ac_import_output.py::_rob_01` |
| AC-ROB-02 | P1 | 已执行 | `test_ac_guards.py::_rob_02` |
| AC-ROB-03 | P1 | 已执行 | `test_ac_guards.py::_rob_03` |
| AC-ROB-04 | P1 | 已执行 | `test_ac_guards.py::_rob_04` |
| AC-ROB-05 | P1 | 已执行 | `test_ac_guards.py::_rob_05` |
| AC-ROB-06 | P2 | 已执行 | `test_ac_guards.py::_rob_06` |
