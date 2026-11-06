-- 2026-11-06 internal identifier rename: course -> series, longform -> piece, lesson -> unit
-- Applies to existing SQLite / PostgreSQL instances; fresh deployments already use the new names.
-- Back up the database before running this.

BEGIN;

-- 1) tables
ALTER TABLE courses            RENAME TO series;
ALTER TABLE lessons            RENAME TO units;
ALTER TABLE lesson_versions    RENAME TO unit_versions;
ALTER TABLE lesson_reviews     RENAME TO unit_reviews;
ALTER TABLE lesson_locks       RENAME TO unit_locks;
ALTER TABLE course_blueprints  RENAME TO series_blueprints;
ALTER TABLE course_grants      RENAME TO series_grants;
ALTER TABLE longforms          RENAME TO pieces;
ALTER TABLE longform_versions  RENAME TO piece_versions;
ALTER TABLE longform_grants    RENAME TO piece_grants;

-- 2) foreign key columns
ALTER TABLE units              RENAME COLUMN course_id   TO series_id;
ALTER TABLE unit_versions      RENAME COLUMN lesson_id   TO unit_id;
ALTER TABLE unit_reviews       RENAME COLUMN lesson_id   TO unit_id;
ALTER TABLE unit_locks         RENAME COLUMN lesson_id   TO unit_id;
ALTER TABLE series_blueprints  RENAME COLUMN course_id   TO series_id;
ALTER TABLE series_grants      RENAME COLUMN course_id   TO series_id;
ALTER TABLE threads            RENAME COLUMN course_id   TO series_id;
ALTER TABLE threads            RENAME COLUMN lesson_id   TO unit_id;
ALTER TABLE piece_versions     RENAME COLUMN longform_id TO piece_id;
ALTER TABLE piece_grants       RENAME COLUMN longform_id TO piece_id;

-- 3) enum values
UPDATE jobs SET kind = 'unit_generate'  WHERE kind = 'lesson_generate';
UPDATE jobs SET kind = 'piece_create'   WHERE kind = 'longform_create';
UPDATE jobs SET kind = 'piece_generate' WHERE kind = 'longform_generate';
UPDATE jobs SET kind = 'piece_rewrite'  WHERE kind = 'longform_rewrite';
UPDATE usage_events SET kind = 'unit'   WHERE kind = 'lesson';
UPDATE usage_events SET kind = 'piece'  WHERE kind = 'longform';
UPDATE share_links SET resource_type = 'series' WHERE resource_type = 'course';
UPDATE share_links SET resource_type = 'piece'  WHERE resource_type = 'longform';

-- 4) primary key and reference prefixes: longform_ -> piece_, lfver_ -> pcver_
UPDATE pieces          SET id        = REPLACE(id, 'longform_', 'piece_')  WHERE id        LIKE 'longform_%';
UPDATE piece_versions  SET piece_id  = REPLACE(piece_id, 'longform_', 'piece_') WHERE piece_id LIKE 'longform_%';
UPDATE piece_grants    SET piece_id  = REPLACE(piece_id, 'longform_', 'piece_') WHERE piece_id LIKE 'longform_%';
UPDATE share_links     SET resource_id = REPLACE(resource_id, 'longform_', 'piece_') WHERE resource_id LIKE 'longform_%';
UPDATE usage_events    SET ref_id    = REPLACE(ref_id, 'longform_', 'piece_') WHERE ref_id LIKE 'longform_%';
UPDATE piece_versions  SET id        = REPLACE(id, 'lfver_', 'pcver_')      WHERE id        LIKE 'lfver_%';

COMMIT;

-- 5) JSON payload keys and ids (REPLACE works the same in SQLite and PostgreSQL)
UPDATE jobs SET payload_json = REPLACE(REPLACE(REPLACE(payload_json, '"course_id"', '"series_id"'), '"lesson_id"', '"unit_id"'), '"longform_id"', '"piece_id"')
  WHERE payload_json LIKE '%course_id%' OR payload_json LIKE '%lesson_id%' OR payload_json LIKE '%longform_id%';
UPDATE jobs SET result_json = REPLACE(REPLACE(REPLACE(result_json, '"course_id"', '"series_id"'), '"lesson_id"', '"unit_id"'), '"longform_id"', '"piece_id"')
  WHERE result_json LIKE '%course_id%' OR result_json LIKE '%lesson_id%' OR result_json LIKE '%longform_id%';
