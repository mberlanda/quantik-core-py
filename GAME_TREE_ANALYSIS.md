# Quantik Game Tree Analysis with Symmetry Reduction

## Depth-wise Analysis
| Depth | Total Legal Moves | Unique Canonical | P0 Wins | P1 Wins | Ongoing | Reduction Factor | Space Savings |
|-------|-------------------|------------------|---------|---------|---------|------------------|---------------|
|     1 |                64 |                3 |       0 |       0 |      64 |           21.33x |         95.3% |
|     2 |             3,392 |               51 |       0 |       0 |   3,392 |           66.51x |         98.5% |
|     3 |           167,552 |              726 |       0 |       0 | 167,552 |          230.79x |         99.6% |
|     4 |         6,776,960 |           10,946 |       0 |   6,912 | 6,770,048 |          619.13x |         99.8% |
|     5 |       231,883,776 |          105,632 | 1,050,624 |       0 | 230,833,152 |         2195.20x |        100.0% |
|     6 |     6,241,600,512 |          901,916 |       0 | 81,653,760 | 6,159,946,752 |         6920.38x |        100.0% |

## Cumulative Analysis
| Metric | Value |
|--------|--------|
| Total Legal Moves | 6,480,432,256 |
| Unique Canonical States | 1,019,274 |
| Player 0 Wins | 1,050,624 |
| Player 1 Wins | 81,660,672 |
| Ongoing Games | 6,397,720,960 |
| Overall Reduction Factor | 6357.89x |
| Overall Space Savings | 100.0% |