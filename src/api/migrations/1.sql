CREATE TABLE IF NOT EXISTS photos (
    id SERIAL PRIMARY KEY,
    created_ts TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_ts TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    bucket INTEGER,
    file_name INTEGER,
    photo_set INTEGER,
    time_lapse_compiled INTEGER,
    file_size INTEGER,

    UNIQUE (image_id, image_build_id, scanner_id)
);
