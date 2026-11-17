select
    feature_key,
    record_hash,
    cast(attributes as json) as attributes,
    snapshot_hash,
    first_seen_at,
    last_seen_at
from main.current_features
