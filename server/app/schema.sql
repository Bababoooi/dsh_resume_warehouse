-- 简历打包与定制生成系统 · SQLite DDL
-- 依据：docs/DATA-MODEL.md（字段名/类型/可空性/约束以该文档为准）
-- 用法：db.init_db() 读取本文件，按 `-- @version N` 分段顺序补齐（幂等）。
-- 隐私红线（写入 schema 便于 code review）：
--   * user_profile.phone / email / photo_path 永不进入任何 LLM payload（consent 层强制 exclude）。
--   * attachment.privacy='private' 的内容（含 data/imports/** 原件）永不进入 LLM payload。
--   * data/** 下的文件只被本地解析器读取，解析结果经用户显式勾选后才可能出网。

-- @version 1

CREATE TABLE IF NOT EXISTS schema_migration (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- UserProfile：单例（id 固定 'me'）。简历头部与文件命名的唯一数据源。
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_profile (
    id             TEXT PRIMARY KEY CHECK (id = 'me'),
    name_zh        TEXT NOT NULL CHECK (length(name_zh) BETWEEN 1 AND 40),
    name_en        TEXT CHECK (name_en IS NULL OR length(name_en) <= 80),
    school_zh      TEXT CHECK (school_zh IS NULL OR length(school_zh) <= 80),
    school_en      TEXT CHECK (school_en IS NULL OR length(school_en) <= 120),
    degree         TEXT CHECK (degree IS NULL OR degree IN ('本科','硕士','博士','大专','其他')),
    major          TEXT CHECK (major IS NULL OR length(major) <= 80),
    grad_year      INTEGER CHECK (grad_year IS NULL OR grad_year BETWEEN 1900 AND 2100),
    phone          TEXT CHECK (phone IS NULL OR phone GLOB '[+0-9 -]*'),
    email          TEXT CHECK (email IS NULL OR (instr(email,'@') > 1 AND instr(email,'.') > 2)),
    city           TEXT,
    available_date TEXT,
    available_note TEXT,
    photo_path     TEXT,
    links_json     TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(links_json)),
    extra_json     TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(extra_json)),
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- Attachment：内容寻址的本地文件（磁盘 data/files/<前2位>/<sha256>.<ext>）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS attachment (
    id            TEXT PRIMARY KEY,
    sha256        TEXT NOT NULL UNIQUE,
    original_name TEXT NOT NULL,
    ext           TEXT NOT NULL,
    mime          TEXT NOT NULL,
    bytes         INTEGER NOT NULL CHECK (bytes >= 0),
    kind          TEXT NOT NULL CHECK (kind IN ('resume_source','photo','evidence','export','other')),
    privacy       TEXT NOT NULL DEFAULT 'private' CHECK (privacy IN ('private','shareable')),
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_attachment_kind ON attachment(kind);
CREATE INDEX IF NOT EXISTS idx_attachment_privacy ON attachment(privacy);

-- ---------------------------------------------------------------------------
-- Package + PackageBulletVariant
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS package (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 120),
    kind            TEXT NOT NULL CHECK (kind IN ('project','internship','education','award','activity','custom')),
    org             TEXT,
    role            TEXT,
    start_date      TEXT,
    end_date        TEXT,
    is_current      INTEGER NOT NULL DEFAULT 0 CHECK (is_current IN (0,1)),
    location        TEXT,
    summary         TEXT CHECK (summary IS NULL OR length(summary) <= 600),
    tech_stack_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(tech_stack_json)),
    tags_json       TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(tags_json)),
    outcomes_json   TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(outcomes_json)),
    evidence_json   TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(evidence_json)),
    status          TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','ready','archived')),
    source          TEXT NOT NULL DEFAULT 'authored' CHECK (source IN ('authored','imported','llm_assisted')),
    content_hash    TEXT,
    deleted_at      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_package_kind ON package(kind);
CREATE INDEX IF NOT EXISTS idx_package_status ON package(status);
CREATE INDEX IF NOT EXISTS idx_package_org ON package(org);
CREATE INDEX IF NOT EXISTS idx_package_deleted ON package(deleted_at);

CREATE TABLE IF NOT EXISTS package_bullet_variant (
    id            TEXT PRIMARY KEY,
    package_id    TEXT NOT NULL REFERENCES package(id) ON DELETE CASCADE,
    bullet_key    TEXT NOT NULL CHECK (length(bullet_key) BETWEEN 1 AND 40),
    text          TEXT NOT NULL CHECK (length(text) BETWEEN 1 AND 400),
    tone          TEXT NOT NULL CHECK (tone IN ('impact','technical','leadership','concise','ats')),
    lang          TEXT NOT NULL CHECK (lang IN ('zh','en')),
    keywords_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(keywords_json)),
    metrics_json  TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(metrics_json)),
    char_len      INTEGER NOT NULL DEFAULT 0,
    llm_generated INTEGER NOT NULL DEFAULT 0 CHECK (llm_generated IN (0,1)),
    verified      INTEGER NOT NULL DEFAULT 0 CHECK (verified IN (0,1)),
    quality_score REAL CHECK (quality_score IS NULL OR (quality_score >= 0 AND quality_score <= 1)),
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    UNIQUE (package_id, bullet_key, tone, lang)
);
CREATE INDEX IF NOT EXISTS idx_variant_package ON package_bullet_variant(package_id);
CREATE INDEX IF NOT EXISTS idx_variant_bullet_key ON package_bullet_variant(package_id, bullet_key);

-- ---------------------------------------------------------------------------
-- Template / TemplateBlock / Slot
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS template (
    id                TEXT PRIMARY KEY,
    name              TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 80),
    source_kind       TEXT NOT NULL CHECK (source_kind IN ('imported_pdf','imported_docx','imported_md','imported_html','builtin')),
    source_file_id    TEXT REFERENCES attachment(id) ON DELETE SET NULL,
    lang              TEXT NOT NULL CHECK (lang IN ('zh','en','mixed')),
    page_limit        INTEGER NOT NULL DEFAULT 1 CHECK (page_limit BETWEEN 1 AND 3),
    layout_json       TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(layout_json)),
    is_default        INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0,1)),
    target_role_family TEXT,
    deleted_at        TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);
-- I2：is_default=1 全局唯一
CREATE UNIQUE INDEX IF NOT EXISTS uq_template_default ON template(is_default) WHERE is_default = 1;

CREATE TABLE IF NOT EXISTS template_block (
    id                 TEXT PRIMARY KEY,
    template_id        TEXT NOT NULL REFERENCES template(id) ON DELETE CASCADE,
    parent_block_id    TEXT REFERENCES template_block(id) ON DELETE CASCADE,
    order_index        INTEGER NOT NULL,
    block_type         TEXT NOT NULL CHECK (block_type IN ('header','summary','section','entry','bullet_list','skills','awards','footer','freeform')),
    heading            TEXT,
    bound_package_kind TEXT CHECK (bound_package_kind IS NULL OR bound_package_kind IN ('project','internship','education','award','activity','custom')),
    style_json         TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(style_json)),
    page_break_before  INTEGER NOT NULL DEFAULT 0 CHECK (page_break_before IN (0,1)),
    max_bullets        INTEGER,
    static_text        TEXT,
    repeat_per_package INTEGER NOT NULL DEFAULT 1 CHECK (repeat_per_package IN (0,1)),
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    UNIQUE (template_id, parent_block_id, order_index)
);
CREATE INDEX IF NOT EXISTS idx_block_template ON template_block(template_id, parent_block_id, order_index);

CREATE TABLE IF NOT EXISTS slot (
    id            TEXT PRIMARY KEY,
    block_id      TEXT NOT NULL REFERENCES template_block(id) ON DELETE CASCADE,
    slot_key      TEXT NOT NULL CHECK (slot_key GLOB '[a-z]*' AND length(slot_key) <= 41),
    slot_type     TEXT NOT NULL CHECK (slot_type IN ('text','longtext','date_range','taglist','url','image','computed')),
    required      INTEGER NOT NULL DEFAULT 0 CHECK (required IN (0,1)),
    bound_field   TEXT,
    default_value TEXT,
    max_chars     INTEGER,
    pattern       TEXT,
    list_source   TEXT CHECK (list_source IS NULL OR list_source IN ('profile.links_json','package.tech_stack_json','package.tags_json')),
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    UNIQUE (block_id, slot_key)
);
CREATE INDEX IF NOT EXISTS idx_slot_block ON slot(block_id);

-- ---------------------------------------------------------------------------
-- ImportJob（导入解析任务；draft 只存在于这里，commit 后才落 Template）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS import_job (
    id                 TEXT PRIMARY KEY,
    attachment_id      TEXT NOT NULL REFERENCES attachment(id) ON DELETE RESTRICT,
    status             TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','parsing','draft','committed','failed')),
    parser             TEXT NOT NULL CHECK (parser IN ('pdf','docx','md','html','txt')),
    draft_json         TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(draft_json)),
    stats_json         TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(stats_json)),
    warnings_json      TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(warnings_json)),
    result_template_id TEXT REFERENCES template(id) ON DELETE SET NULL,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_import_status ON import_job(status);

-- ---------------------------------------------------------------------------
-- JobDescription / JDRequirement
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS job_description (
    id              TEXT PRIMARY KEY,
    title           TEXT CHECK (title IS NULL OR length(title) <= 120),
    company_name    TEXT CHECK (company_name IS NULL OR length(company_name) <= 120),
    raw_text        TEXT NOT NULL,
    attachment_id   TEXT REFERENCES attachment(id) ON DELETE SET NULL,
    source_url      TEXT,
    lang            TEXT NOT NULL DEFAULT 'zh' CHECK (lang IN ('zh','en')),
    analysis_status TEXT NOT NULL DEFAULT 'none' CHECK (analysis_status IN ('none','analyzing','done','failed')),
    analysis_method TEXT CHECK (analysis_method IS NULL OR analysis_method IN ('llm','heuristic','manual')),
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jd_company ON job_description(company_name);

CREATE TABLE IF NOT EXISTS jd_requirement (
    id                       TEXT PRIMARY KEY,
    jd_id                    TEXT NOT NULL REFERENCES job_description(id) ON DELETE CASCADE,
    skill                    TEXT NOT NULL CHECK (length(skill) <= 80),
    category                 TEXT NOT NULL CHECK (category IN ('hard','soft','domain','tool','language','certificate')),
    priority                 TEXT NOT NULL CHECK (priority IN ('must','should','nice')),
    weight                   REAL NOT NULL DEFAULT 0.5 CHECK (weight >= 0 AND weight <= 1),
    evidence_hint            TEXT CHECK (evidence_hint IS NULL OR length(evidence_hint) <= 200),
    raw_quote                TEXT CHECK (raw_quote IS NULL OR length(raw_quote) <= 300),
    source                   TEXT NOT NULL CHECK (source IN ('llm','heuristic','manual')),
    matched_package_ids_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(matched_package_ids_json)),
    created_at               TEXT NOT NULL,
    updated_at               TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_jd_requirement ON jd_requirement(jd_id, lower(skill), category);

-- ---------------------------------------------------------------------------
-- CompanyProfile（只由 JD + 公司名 + 用户笔记推导，不抓网页）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS company_profile (
    id                      TEXT PRIMARY KEY,
    company_name            TEXT NOT NULL UNIQUE,
    industry                TEXT,
    company_stage           TEXT,
    size_hint               TEXT,
    culture_signals_json    TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(culture_signals_json)),
    hiring_preferences_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(hiring_preferences_json)),
    interview_focus_json    TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(interview_focus_json)),
    tone                    TEXT,
    keywords_json           TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(keywords_json)),
    sources_json            TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(sources_json)),
    confidence              REAL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    method                  TEXT CHECK (method IS NULL OR method IN ('llm','heuristic','manual')),
    last_analyzed_at        TEXT,
    expires_at              TEXT,
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- ResumeBuild / BuildSelection / BuildArtifact
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS resume_build (
    id                   TEXT PRIMARY KEY,
    name                 TEXT NOT NULL CHECK (length(name) <= 120),
    template_id          TEXT NOT NULL REFERENCES template(id) ON DELETE RESTRICT,
    jd_id                TEXT REFERENCES job_description(id) ON DELETE SET NULL,
    company_profile_id   TEXT REFERENCES company_profile(id) ON DELETE SET NULL,
    position             TEXT CHECK (position IS NULL OR length(position) <= 80),
    company              TEXT CHECK (company IS NULL OR length(company) <= 80),
    lang                 TEXT NOT NULL DEFAULT 'zh' CHECK (lang IN ('zh','en')),
    status               TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','assembled','exported','failed')),
    naming_pattern       TEXT NOT NULL DEFAULT '{position}-{name}-{school}',
    naming_overrides_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(naming_overrides_json)),
    field_values_json    TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(field_values_json)),
    sections_order_json  TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(sections_order_json)),
    warnings_json        TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(warnings_json)),
    est_pages            REAL,
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_build_template ON resume_build(template_id);
CREATE INDEX IF NOT EXISTS idx_build_status ON resume_build(status);

CREATE TABLE IF NOT EXISTS build_selection (
    id                TEXT PRIMARY KEY,
    build_id          TEXT NOT NULL REFERENCES resume_build(id) ON DELETE CASCADE,
    package_id        TEXT NOT NULL,
    variant_ids_json  TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(variant_ids_json)),
    order_index       INTEGER NOT NULL DEFAULT 0,
    overrides_json    TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(overrides_json)),
    snapshot_json     TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(snapshot_json)),
    created_at        TEXT NOT NULL,
    UNIQUE (build_id, package_id)
);
CREATE INDEX IF NOT EXISTS idx_selection_build ON build_selection(build_id, order_index);

CREATE TABLE IF NOT EXISTS build_artifact (
    id             TEXT PRIMARY KEY,
    build_id       TEXT NOT NULL REFERENCES resume_build(id) ON DELETE CASCADE,
    format         TEXT NOT NULL CHECK (format IN ('pdf','docx','html','md')),
    engine         TEXT NOT NULL CHECK (engine IN ('reportlab','chrome','docx','jinja2')),
    filename       TEXT NOT NULL,
    rel_path       TEXT NOT NULL,
    bytes          INTEGER NOT NULL CHECK (bytes >= 0),
    sha256         TEXT NOT NULL,
    text_verified  INTEGER CHECK (text_verified IS NULL OR text_verified IN (0,1)),
    text_diff_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(text_diff_json)),
    warnings_json  TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(warnings_json)),
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_artifact_build ON build_artifact(build_id, created_at);

-- ---------------------------------------------------------------------------
-- 支撑表：Job / LlmPreview / LlmCallLog / AppSetting
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS job (
    id          TEXT PRIMARY KEY,
    kind        TEXT NOT NULL CHECK (kind IN ('import_parse','jd_analyze','company_analyze','bullets_generate','build_export','build_batch')),
    status      TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','succeeded','failed','interrupted')),
    progress    INTEGER NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
    message     TEXT,
    result_json TEXT CHECK (result_json IS NULL OR json_valid(result_json)),
    error_json  TEXT CHECK (error_json IS NULL OR json_valid(error_json)),
    created_at  TEXT NOT NULL,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_job_status ON job(status, created_at);

-- consent 状态机：服务端唯一真源（I5：pending → consumed/expired/rejected 不可逆）
CREATE TABLE IF NOT EXISTS llm_preview (
    id                   TEXT PRIMARY KEY,
    purpose              TEXT NOT NULL CHECK (purpose IN ('jd_analyze','bullets_generate','company_profile','build_suggest','summary_polish')),
    provider             TEXT NOT NULL,
    model                TEXT NOT NULL,
    endpoint_host        TEXT NOT NULL,
    payload_json         TEXT NOT NULL CHECK (json_valid(payload_json)),
    payload_sha256       TEXT NOT NULL,
    field_manifest_json  TEXT NOT NULL CHECK (json_valid(field_manifest_json)),
    est_tokens           INTEGER NOT NULL DEFAULT 0,
    redactions_json      TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(redactions_json)),
    status               TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','consumed','expired','rejected')),
    consumed_at          TEXT,
    expires_at           TEXT NOT NULL,
    created_at           TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_preview_status ON llm_preview(status, expires_at);

-- 出网审计：只记字段名，不记正文
CREATE TABLE IF NOT EXISTS llm_call_log (
    id               TEXT PRIMARY KEY,
    preview_id       TEXT REFERENCES llm_preview(id) ON DELETE SET NULL,
    provider         TEXT NOT NULL,
    model            TEXT NOT NULL,
    endpoint_host    TEXT NOT NULL,
    field_names_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(field_names_json)),
    payload_bytes    INTEGER NOT NULL DEFAULT 0,
    est_tokens       INTEGER NOT NULL DEFAULT 0,
    http_status      INTEGER,
    latency_ms       INTEGER,
    ok               INTEGER NOT NULL DEFAULT 0 CHECK (ok IN (0,1)),
    error_code       TEXT,
    created_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_llm_call_created ON llm_call_log(created_at);

-- AppSetting：UI 偏好与全局配置（**不存 API key**，key 只在 .env）
CREATE TABLE IF NOT EXISTS app_setting (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at TEXT NOT NULL
);

-- @version 2
-- 全文检索：package_fts 由 DAO 在写包/写变体后重建（中文用 bigram 预切分写入 search 列）。
-- 为什么不用外部内容表：variant 文本来自另一张表，聚合逻辑放 Python 更可控。
CREATE VIRTUAL TABLE IF NOT EXISTS package_fts USING fts5(
    package_id UNINDEXED,
    package_title,
    org,
    role,
    variant_text,
    tags_text,
    tokenize = 'unicode61 remove_diacritics 2'
);

-- 软/硬删除包时同步清掉索引行（variant 由 ON DELETE CASCADE 清理，索引由 DAO 重建）
CREATE TRIGGER IF NOT EXISTS trg_package_fts_delete
AFTER DELETE ON package
BEGIN
    DELETE FROM package_fts WHERE package_id = OLD.id;
END;

-- @version 3
-- 默认设置（DATA-MODEL §14.4）。INSERT OR IGNORE 保证幂等、不覆盖用户改动。
INSERT OR IGNORE INTO app_setting(key, value, updated_at) VALUES
    ('naming_template', '"{position}-{name}-{school}"', strftime('%Y-%m-%dT%H:%M:%S+08:00','now','localtime')),
    ('default_engine',   '"auto"',                       strftime('%Y-%m-%dT%H:%M:%S+08:00','now','localtime')),
    ('verify_text',      'true',                         strftime('%Y-%m-%dT%H:%M:%S+08:00','now','localtime')),
    ('page_limit',       '1',                            strftime('%Y-%m-%dT%H:%M:%S+08:00','now','localtime')),
    ('theme',            '"light"',                      strftime('%Y-%m-%dT%H:%M:%S+08:00','now','localtime')),
    ('auto_redact',      '["phone","email","id","name"]',            strftime('%Y-%m-%dT%H:%M:%S+08:00','now','localtime')),
    ('last_template_id', 'null',                         strftime('%Y-%m-%dT%H:%M:%S+08:00','now','localtime')),
    ('schema_version',   '3',                            strftime('%Y-%m-%dT%H:%M:%S+08:00','now','localtime'));

-- @version 4
-- 职业技能：展示层与索引层分离（用户 2026-10-23 裁决：简历上保持整句原文，禁止 tag 块）。
--   line   = 唯一渲染源（逐字原文），tokens = 派生索引（只给 JD 匹配用，允许重建、禁止渲染）
ALTER TABLE user_profile ADD COLUMN skills_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(skills_json));
UPDATE app_setting SET value = '4', updated_at = strftime('%Y-%m-%dT%H:%M:%S+08:00','now','localtime') WHERE key = 'schema_version';

-- @version 5
-- t7（JD / 公司偏好分析）+ 导入历史可删除（captain m02126 ③）。
--   user_profile.school_tier       ：院校层次升为一等列（DATA-MODEL v1.6），供 competitiveness 直接取用，
--                                    不再藏在 extra_json 里（藏起来就没人消费 = 净损失）。
--   job_description.competitiveness：§6.1 契约必需字段，校名必须真的被消费（ADR-20 / D-19）。
--   company_profile.school_preference：§7 院校偏好，含反编造要求（JD 没提就不得判硬卡）。
--   jd_requirement.candidate_status ：逐条对照候选人现状；source 记录是 LLM 判的还是启发式判的。
--   import_job.deleted_at          ：导入历史此前**无法删除**（没有列），只能硬删用户数据；
--                                    加软删列后 GET /imports 默认过滤，DELETE 只解绑。
ALTER TABLE user_profile ADD COLUMN school_tier TEXT
    CHECK (school_tier IS NULL OR school_tier IN ('C9','985','211','双一流','普通本科','海外','其他'));
ALTER TABLE job_description ADD COLUMN competitiveness_json TEXT NOT NULL DEFAULT '{}'
    CHECK (json_valid(competitiveness_json));
ALTER TABLE company_profile ADD COLUMN school_preference_json TEXT NOT NULL DEFAULT '{}'
    CHECK (json_valid(school_preference_json));
ALTER TABLE jd_requirement ADD COLUMN candidate_status TEXT
    CHECK (candidate_status IS NULL OR candidate_status IN ('satisfied','partial','missing'));
ALTER TABLE jd_requirement ADD COLUMN candidate_status_source TEXT
    CHECK (candidate_status_source IS NULL OR candidate_status_source IN ('llm','heuristic','manual'));
ALTER TABLE import_job ADD COLUMN deleted_at TEXT;
CREATE INDEX IF NOT EXISTS idx_import_job_deleted ON import_job(deleted_at);
CREATE INDEX IF NOT EXISTS idx_jd_requirement_jd ON jd_requirement(jd_id);
UPDATE app_setting SET value = '5', updated_at = strftime('%Y-%m-%dT%H:%M:%S+08:00','now','localtime') WHERE key = 'schema_version';

-- ---------------------------------------------------------------------------
-- @version 6：公司主页 URL 一等列
-- ---------------------------------------------------------------------------
-- 契约 §7 要求：没给 url 时「只在 company_profile.website 已知时才抓」。
-- 之前没有这一列，只能把网址塞进 sources_json 里猜，等于没实现这条规则。
-- ---------------------------------------------------------------------------
ALTER TABLE company_profile ADD COLUMN website TEXT;
UPDATE app_setting SET value = '6', updated_at = strftime('%Y-%m-%dT%H:%M:%S+08:00','now','localtime') WHERE key = 'schema_version';

-- ---------------------------------------------------------------------------
-- @version 7：变体语气新增 original（导入原文照录）
-- ---------------------------------------------------------------------------
-- 用户在导入确认时把简历原文落成变体，语气既不是 impact 也不是 ats，而是「原文照录」。
-- 之前把 original 硬塞进 impact 会污染后续改写与匹配的语义。
-- SQLite 不支持修改 CHECK，只能重建表（先在临时名上建、搬数据、换名、补索引）。
-- ---------------------------------------------------------------------------
CREATE TABLE package_bullet_variant_v7 (
    id            TEXT PRIMARY KEY,
    package_id    TEXT NOT NULL REFERENCES package(id) ON DELETE CASCADE,
    bullet_key    TEXT NOT NULL CHECK (length(bullet_key) BETWEEN 1 AND 40),
    text          TEXT NOT NULL CHECK (length(text) BETWEEN 1 AND 400),
    tone          TEXT NOT NULL CHECK (tone IN ('impact','technical','leadership','concise','ats','original')),
    lang          TEXT NOT NULL CHECK (lang IN ('zh','en')),
    keywords_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(keywords_json)),
    metrics_json  TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(metrics_json)),
    char_len      INTEGER NOT NULL DEFAULT 0,
    llm_generated INTEGER NOT NULL DEFAULT 0 CHECK (llm_generated IN (0,1)),
    verified      INTEGER NOT NULL DEFAULT 0 CHECK (verified IN (0,1)),
    quality_score REAL CHECK (quality_score IS NULL OR (quality_score >= 0 AND quality_score <= 1)),
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    UNIQUE (package_id, bullet_key, tone, lang)
);
INSERT INTO package_bullet_variant_v7
    SELECT id, package_id, bullet_key, text, tone, lang, keywords_json, metrics_json,
           char_len, llm_generated, verified, quality_score, created_at, updated_at
      FROM package_bullet_variant;
DROP TABLE package_bullet_variant;
ALTER TABLE package_bullet_variant_v7 RENAME TO package_bullet_variant;
CREATE INDEX IF NOT EXISTS idx_variant_package ON package_bullet_variant(package_id);
CREATE INDEX IF NOT EXISTS idx_variant_bullet_key ON package_bullet_variant(package_id, bullet_key);
UPDATE app_setting SET value = '7', updated_at = strftime('%Y-%m-%dT%H:%M:%S+08:00','now','localtime') WHERE key = 'schema_version';

-- ---------------------------------------------------------------------------
-- @version 8：导入派生包的溯源列 + LLM 调用日志的 purpose
-- ---------------------------------------------------------------------------
-- ① DATA-MODEL v1.12 起 `package` 就声明了 `source_import_job_id` /
--    `source_entry_temp_id` 与部分唯一索引，但 schema 从未建过这两列 —— 纯文档漂移：
--    代码只能拿 tags 里的 `import:<id>` / `entry:<temp_id>` 当幂等键（用户可见的 tags 被塞了
--    机器键，且契约里的 UNIQUE 约束形同虚设）。这里补列 + 补索引，实现侧再改成写真实列。
-- ② `llm_call_log` 一直没有 `purpose`：调用点知道 purpose、却只能靠 preview_id 反查
--    （preview 过期/清理后就查不出「这次调用是 jd_analyze 还是 bullets_generate」，
--    也就无法证实「分析档走 LLM_MODEL_ANALYSIS」）。加一等列，历史行保持 NULL（可解释）。
-- 幂等性：本段只由 migrate() 对每个库执行一次（schema_migration 记账），重复执行不会重放；
-- 对存量 30 行 import_job 与 5 条 imported 包只加列、不改数据（回填由独立脚本完成）。
-- ---------------------------------------------------------------------------
ALTER TABLE package ADD COLUMN source_import_job_id TEXT;
ALTER TABLE package ADD COLUMN source_entry_temp_id TEXT;
CREATE INDEX IF NOT EXISTS idx_package_source_job ON package(source_import_job_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_package_source_entry
    ON package(source_import_job_id, source_entry_temp_id)
    WHERE source_import_job_id IS NOT NULL AND source_entry_temp_id IS NOT NULL;

ALTER TABLE llm_call_log ADD COLUMN purpose TEXT;
CREATE INDEX IF NOT EXISTS idx_llm_call_purpose ON llm_call_log(purpose, created_at);
UPDATE app_setting SET value = '8', updated_at = strftime('%Y-%m-%dT%H:%M:%S+08:00','now','localtime') WHERE key = 'schema_version';

-- ---------------------------------------------------------------------------
-- @version 9：变体来源可区分（AC-PKG-14）
-- ---------------------------------------------------------------------------
-- 原文即事实的变体（导入照录）与 LLM 改写出来的变体，可信度完全不同：
-- 前者 `verified=1`，后者必须 `verified=0` 并在 UI 标「AI 改写·待确认」。
-- 但在此之前两者在库里无法区分（只有 llm_generated 0/1，手工补写的也落在 0）。
-- 这里加 `source`：imported_verbatim / llm_rewrite / manual；
-- 存量行按 llm_generated 回填，保证 `source` 永不为空。
-- ---------------------------------------------------------------------------
ALTER TABLE package_bullet_variant ADD COLUMN source TEXT
    CHECK (source IS NULL OR source IN ('imported_verbatim', 'llm_rewrite', 'manual'));
UPDATE package_bullet_variant
   SET source = CASE WHEN COALESCE(llm_generated, 0) = 1 THEN 'llm_rewrite' ELSE 'imported_verbatim' END
 WHERE source IS NULL;
UPDATE app_setting SET value = '9', updated_at = strftime('%Y-%m-%dT%H:%M:%S+08:00','now','localtime') WHERE key = 'schema_version';

-- ---------------------------------------------------------------------------
-- @version 10：requirement 的现状判定允许「本机否决」（local_override）
-- ---------------------------------------------------------------------------
-- JD 分析是两段式：先由模型给出 candidate_status，再由本机按仓库/档案证据复核。
-- 复核会否决「明明有证据却说没有」的判定，这次否决必须留下痕迹，否则用户会以为
-- 是模型自己改的主意。SQLite 不能改 CHECK，只能重建表。
-- ---------------------------------------------------------------------------
CREATE TABLE jd_requirement_v10 (
    id                       TEXT PRIMARY KEY,
    jd_id                    TEXT NOT NULL REFERENCES job_description(id) ON DELETE CASCADE,
    skill                    TEXT NOT NULL CHECK (length(skill) <= 80),
    category                 TEXT NOT NULL CHECK (category IN ('hard','soft','domain','tool','language','certificate')),
    priority                 TEXT NOT NULL CHECK (priority IN ('must','should','nice')),
    weight                   REAL NOT NULL DEFAULT 0.5 CHECK (weight >= 0 AND weight <= 1),
    evidence_hint            TEXT CHECK (evidence_hint IS NULL OR length(evidence_hint) <= 200),
    raw_quote                TEXT CHECK (raw_quote IS NULL OR length(raw_quote) <= 300),
    source                   TEXT NOT NULL CHECK (source IN ('llm','heuristic','manual')),
    matched_package_ids_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(matched_package_ids_json)),
    created_at               TEXT NOT NULL,
    updated_at               TEXT NOT NULL,
    candidate_status         TEXT CHECK (candidate_status IS NULL OR candidate_status IN ('satisfied','partial','missing')),
    candidate_status_source  TEXT CHECK (candidate_status_source IS NULL OR candidate_status_source IN ('llm','heuristic','manual','local_override'))
);
INSERT INTO jd_requirement_v10 (
    id, jd_id, skill, category, priority, weight, evidence_hint, raw_quote,
    source, matched_package_ids_json, created_at, updated_at,
    candidate_status, candidate_status_source
)
SELECT
    id, jd_id, skill, category, priority, weight, evidence_hint, raw_quote,
    source, matched_package_ids_json, created_at, updated_at,
    candidate_status, candidate_status_source
FROM jd_requirement;
DROP TABLE jd_requirement;
ALTER TABLE jd_requirement_v10 RENAME TO jd_requirement;
CREATE UNIQUE INDEX IF NOT EXISTS uq_jd_requirement ON jd_requirement(jd_id, lower(skill), category);
CREATE INDEX IF NOT EXISTS idx_jd_requirement_jd ON jd_requirement(jd_id);
UPDATE app_setting SET value = '10', updated_at = strftime('%Y-%m-%dT%H:%M:%S+08:00','now','localtime') WHERE key = 'schema_version';

-- ---------------------------------------------------------------------------
-- v11（2026-10-23）：jd_requirement 增加 matched_evidence_json。
--
-- 为什么：v10 只有 `matched_package_ids_json`（哪几个包命中），用户问「凭什么说
-- 我满足」时答不出来。§6.2.4 / I21 要求每条判定都能回溯到三源之一
-- （package 变体原文 / skills_json 行 / 档案字段），并带 ≥8 字原文引文。
-- ---------------------------------------------------------------------------
-- @version 11
ALTER TABLE jd_requirement ADD COLUMN matched_evidence_json TEXT NOT NULL DEFAULT '[]';
UPDATE app_setting SET value = '11', updated_at = strftime('%Y-%m-%dT%H:%M:%S+08:00','now','localtime') WHERE key = 'schema_version';

-- ---------------------------------------------------------------------------
-- @version 12
-- 构建记录的「归档」语义（t15 返工：prune 默认只能归档，不能直接抹掉用户历史）
-- ---------------------------------------------------------------------------
-- 之前的 prune 脚本只能硬删，因为这张表没有任何「隐藏但保留」的列——一条命令就把
-- 用户导出的历史弄没了，且不可恢复。归档 ≠ 删除：行仍在、产物仍在，只是默认列表
-- 不再显示，`?include_archived=1` 还能看回来。真删必须显式 --hard-delete --yes。
ALTER TABLE resume_build ADD COLUMN archived_at TEXT;

CREATE INDEX IF NOT EXISTS idx_build_archived ON resume_build(archived_at);

UPDATE app_setting SET value = '12', updated_at = strftime('%Y-%m-%dT%H:%M:%S+08:00','now','localtime') WHERE key = 'schema_version';
