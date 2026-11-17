select
    s.snapshot_hash,
    s.source_url,
    s.downloaded_at,
    s.row_count,
    count(o.feature_key) as observed_features
from main.snapshots s
left join main.feature_observations o using (snapshot_hash)
group by 1, 2, 3, 4
