# Provider Allowlist PR Evidence Bundle

**Nothing was applied.** This checksum-bound report only gathers and verifies existing review evidence. It does not edit provider policy, allowlist a provider, promote staging, run providers, generate picks, place bets, or enable cron.

## Bundle verdict

- **Evidence bundle ready for PR review**
- Provider: **the_odds_api** (`odds_api`)
- Bundle ID: `odds_api-allowlist-evidence-620b48a474bd4546`
- Bundle SHA-256: `620b48a474bd4546c6f1cccf79f3cfde907ba8dfcf4b90a24df462504bb08247`
- Included checksum entries: **57**

## Review decisions

- Preview verdict: **Ready for separate allowlist PR**
- Conformance verdict: **Conforms to preview**
- Receipt verification verdict: **Verified for allowlist PR review**
- Human receipt ID: `odds_api-20260821T114655-0400-20ffa5677988`
- Checklist verdict: **Ready for human allowlist review**

## Included evidence and status

| evidence_type                                  | evidence_path                                                                                          | required   | expected_checksum_sha256                                         | current_checksum_sha256                                          | status   | verdict                          | generated_at              | details                                                                                                       |
|:-----------------------------------------------|:-------------------------------------------------------------------------------------------------------|:-----------|:-----------------------------------------------------------------|:-----------------------------------------------------------------|:---------|:---------------------------------|:--------------------------|:--------------------------------------------------------------------------------------------------------------|
| provider_allowlist_pr_preview                  | data/outputs/provider_allowlist_pr_preview.json                                                        | Yes        |                                                                  | a5c7969546abfa8fedecb0359017e6c29e73362fc888740a2480d94e7895322f | Included | Ready for separate allowlist PR  | 2026-08-21T11:54:32-04:00 | Current checksum matches every available binding.                                                             |
| provider_human_acceptance_receipt_verification | data/outputs/provider_human_acceptance_receipt_verification.json                                       | Yes        | a5b59887648b80bd03f4ee8e04d7e6f68281497a7e18d3beac80bb77fc3a51fd | a5b59887648b80bd03f4ee8e04d7e6f68281497a7e18d3beac80bb77fc3a51fd | Included | Verified for allowlist PR review | 2026-08-21T11:47:03-04:00 | Current checksum matches every available binding.                                                             |
| provider_human_acceptance_receipt              | data/outputs/provider_human_acceptance_receipt.json                                                    | Yes        | 5ffec591e5ade9f3d74130b81e7ca7ebafdba5539b17fef758ad630291c81836 | 5ffec591e5ade9f3d74130b81e7ca7ebafdba5539b17fef758ad630291c81836 | Included | approved_for_allowlist_pr        |                           | Current checksum matches every available binding.                                                             |
| provider_acceptance_checklist                  | data/outputs/provider_acceptance_checklist.json                                                        | Yes        | 865d4e6ec1c4d1535a96966bba04df89ce3a0643e288cde36a3c5b643aac4b69 | 865d4e6ec1c4d1535a96966bba04df89ce3a0643e288cde36a3c5b643aac4b69 | Included | Ready for human allowlist review | 2026-08-21T11:44:26-04:00 | Current checksum matches every available binding.                                                             |
| reviewed_shadow_archive_bundle                 | data/outputs/archive/provider_shadow_runs/2026-08-21/154335_odds_api                                   | Yes        | 6b2842cbc84eddbecbd3ca435a652bc900f47c2b00999985ce398c47059aa866 | 6b2842cbc84eddbecbd3ca435a652bc900f47c2b00999985ce398c47059aa866 | Included | Shadow ready for review          | 2026-08-21T15:43:35+00:00 | Current checksum matches every available binding. Archive contains 9 file(s).                                 |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/154335_odds_api/archive_metadata.json             | Yes        | 00a8ed2f5e471c240b7333af072afdb4d96ff2bbb3737c3dc661977a52d6f9cc | 00a8ed2f5e471c240b7333af072afdb4d96ff2bbb3737c3dc661977a52d6f9cc | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `archive_metadata.json`.             |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/154335_odds_api/provider_run_report.json          | Yes        | bef6bd5c9af16226774580da6b204d1cedf055d27834b4241b985d45a747a892 | bef6bd5c9af16226774580da6b204d1cedf055d27834b4241b985d45a747a892 | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_run_report.json`.          |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/154335_odds_api/provider_run_report.md            | Yes        | e58ae4ab3612cbde9043de6445d4b6f24bf1124d5db4e350377ea14b793b2b1a | e58ae4ab3612cbde9043de6445d4b6f24bf1124d5db4e350377ea14b793b2b1a | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_run_report.md`.            |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/154335_odds_api/provider_shadow_verification.csv  | Yes        | df25ef586a3eb596e5003ee6dce8b1b4decf509876dd5bd8864bb0988167aba4 | df25ef586a3eb596e5003ee6dce8b1b4decf509876dd5bd8864bb0988167aba4 | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_shadow_verification.csv`.  |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/154335_odds_api/provider_shadow_verification.json | Yes        | e9afa9b87bbbab56915eb2fa336d611975ce7ed81dbdb26777698d947085ead9 | e9afa9b87bbbab56915eb2fa336d611975ce7ed81dbdb26777698d947085ead9 | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_shadow_verification.json`. |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/154335_odds_api/provider_shadow_verification.md   | Yes        | 478ed0325f094cc5e97e24cb20d0e872183396a2a3d357bc279bb84da9754b2d | 478ed0325f094cc5e97e24cb20d0e872183396a2a3d357bc279bb84da9754b2d | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_shadow_verification.md`.   |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/154335_odds_api/staging_input_validation.csv      | Yes        | 7df1af4bd9314f2d585e4e1512236957cca48076610127b2f9fb47379a046bb0 | 7df1af4bd9314f2d585e4e1512236957cca48076610127b2f9fb47379a046bb0 | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `staging_input_validation.csv`.      |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/154335_odds_api/staging_input_validation.json     | Yes        | 6b06bae57bcdb61f2296012ed70453b20fac85c822136130f129a71d37a3075d | 6b06bae57bcdb61f2296012ed70453b20fac85c822136130f129a71d37a3075d | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `staging_input_validation.json`.     |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/154335_odds_api/staging_input_validation.md       | Yes        | ba53f53f5554ca9a5387018b1f48a02d15cffb97b6075187289e196c2cace9f5 | ba53f53f5554ca9a5387018b1f48a02d15cffb97b6075187289e196c2cace9f5 | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `staging_input_validation.md`.       |
| reviewed_shadow_archive_bundle                 | data/outputs/archive/provider_shadow_runs/2026-08-21/154222_odds_api                                   | Yes        | 539a2672fc06e78616e8235fecd39d85a9c67d697350547a6a20f80d0c197c28 | 539a2672fc06e78616e8235fecd39d85a9c67d697350547a6a20f80d0c197c28 | Included | Shadow ready for review          | 2026-08-21T15:42:22+00:00 | Current checksum matches every available binding. Archive contains 9 file(s).                                 |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/154222_odds_api/archive_metadata.json             | Yes        | e4a87d50ebc2f7cb5747c10b364363135f30c0c387b203f29ce389d215c5c117 | e4a87d50ebc2f7cb5747c10b364363135f30c0c387b203f29ce389d215c5c117 | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `archive_metadata.json`.             |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/154222_odds_api/provider_run_report.json          | Yes        | b3695687f7cf887af4234784d106698e11ccefa98e342425640d0cdced1d5ff5 | b3695687f7cf887af4234784d106698e11ccefa98e342425640d0cdced1d5ff5 | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_run_report.json`.          |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/154222_odds_api/provider_run_report.md            | Yes        | 011c5d2360df796195efa3bbd82fa5a805baaeb570d6cc79e24d335ad3c79741 | 011c5d2360df796195efa3bbd82fa5a805baaeb570d6cc79e24d335ad3c79741 | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_run_report.md`.            |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/154222_odds_api/provider_shadow_verification.csv  | Yes        | 148f77319e90180102c53481c663ac11d88e00f35da708e6f158116b599775e8 | 148f77319e90180102c53481c663ac11d88e00f35da708e6f158116b599775e8 | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_shadow_verification.csv`.  |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/154222_odds_api/provider_shadow_verification.json | Yes        | 9a0413dfe47a92e0178178c86f186205e67d5c1341a2ee0f28f96ec5810d5c99 | 9a0413dfe47a92e0178178c86f186205e67d5c1341a2ee0f28f96ec5810d5c99 | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_shadow_verification.json`. |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/154222_odds_api/provider_shadow_verification.md   | Yes        | 1c5fda77240e8f0ed68938927c1ace8cb9396c8d39cc182cb34a0e0c6ae34e48 | 1c5fda77240e8f0ed68938927c1ace8cb9396c8d39cc182cb34a0e0c6ae34e48 | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_shadow_verification.md`.   |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/154222_odds_api/staging_input_validation.csv      | Yes        | 7df1af4bd9314f2d585e4e1512236957cca48076610127b2f9fb47379a046bb0 | 7df1af4bd9314f2d585e4e1512236957cca48076610127b2f9fb47379a046bb0 | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `staging_input_validation.csv`.      |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/154222_odds_api/staging_input_validation.json     | Yes        | 75def9eb58b441c87aeebc5fa03b12a5118428dc809f559c7cd48645987feeaf | 75def9eb58b441c87aeebc5fa03b12a5118428dc809f559c7cd48645987feeaf | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `staging_input_validation.json`.     |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/154222_odds_api/staging_input_validation.md       | Yes        | 68e866e730e1df7e8db1e507ce0319d16473d902fe585fa2344f7cf5a24c509a | 68e866e730e1df7e8db1e507ce0319d16473d902fe585fa2344f7cf5a24c509a | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `staging_input_validation.md`.       |
| reviewed_shadow_archive_bundle                 | data/outputs/archive/provider_shadow_runs/2026-08-21/154019_odds_api                                   | Yes        | 9525c7de23a88ac19b34b9e812e68b6caa156d5d3483f9360b12edfc3c262935 | 9525c7de23a88ac19b34b9e812e68b6caa156d5d3483f9360b12edfc3c262935 | Included | Shadow ready for review          | 2026-08-21T15:40:19+00:00 | Current checksum matches every available binding. Archive contains 9 file(s).                                 |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/154019_odds_api/archive_metadata.json             | Yes        | 74ab893d1efbde34329b9df97b82803e14967b7e326c519d4f7526b9be2c7038 | 74ab893d1efbde34329b9df97b82803e14967b7e326c519d4f7526b9be2c7038 | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `archive_metadata.json`.             |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/154019_odds_api/provider_run_report.json          | Yes        | 4536fcca99fe06c8f911231ca49dbd0bcf0ee18983c495d33e782a572dc601d6 | 4536fcca99fe06c8f911231ca49dbd0bcf0ee18983c495d33e782a572dc601d6 | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_run_report.json`.          |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/154019_odds_api/provider_run_report.md            | Yes        | 527c90d02e1be6b126fa3cd7987ae23097e0b3e067eaf762e3275651a09ae76d | 527c90d02e1be6b126fa3cd7987ae23097e0b3e067eaf762e3275651a09ae76d | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_run_report.md`.            |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/154019_odds_api/provider_shadow_verification.csv  | Yes        | d4c9aa228517a4b0487d82e131110d9bb426bdefa540cc895e36057f14ccd3f2 | d4c9aa228517a4b0487d82e131110d9bb426bdefa540cc895e36057f14ccd3f2 | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_shadow_verification.csv`.  |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/154019_odds_api/provider_shadow_verification.json | Yes        | 73899e80687c4db501eeaed0a068ffd7dff943b7e0b18e0f7185ff1b685b847b | 73899e80687c4db501eeaed0a068ffd7dff943b7e0b18e0f7185ff1b685b847b | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_shadow_verification.json`. |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/154019_odds_api/provider_shadow_verification.md   | Yes        | 1d0e3b710dfddb0b0e26cf9e05e14fd83eb4d4be17cfe7bb98d4ecb20f3d04f8 | 1d0e3b710dfddb0b0e26cf9e05e14fd83eb4d4be17cfe7bb98d4ecb20f3d04f8 | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_shadow_verification.md`.   |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/154019_odds_api/staging_input_validation.csv      | Yes        | 7df1af4bd9314f2d585e4e1512236957cca48076610127b2f9fb47379a046bb0 | 7df1af4bd9314f2d585e4e1512236957cca48076610127b2f9fb47379a046bb0 | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `staging_input_validation.csv`.      |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/154019_odds_api/staging_input_validation.json     | Yes        | b68af8ad108e0706f1c10c20371c6bbd3ad4f01975b9c8d57406728813c3e08f | b68af8ad108e0706f1c10c20371c6bbd3ad4f01975b9c8d57406728813c3e08f | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `staging_input_validation.json`.     |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/154019_odds_api/staging_input_validation.md       | Yes        | ee039aa0ed52cd8f0e8be3efb1e0c163e34a10f8f0e0d2eb9f0b48ecdfa02518 | ee039aa0ed52cd8f0e8be3efb1e0c163e34a10f8f0e0d2eb9f0b48ecdfa02518 | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `staging_input_validation.md`.       |
| reviewed_shadow_archive_bundle                 | data/outputs/archive/provider_shadow_runs/2026-08-21/153908_odds_api                                   | Yes        | 0e0aae3c2da51bf78bd25991ad100e5421195356ff9f3fa8bc2c8c1bae411398 | 0e0aae3c2da51bf78bd25991ad100e5421195356ff9f3fa8bc2c8c1bae411398 | Included | Shadow ready for review          | 2026-08-21T15:39:08+00:00 | Current checksum matches every available binding. Archive contains 9 file(s).                                 |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/153908_odds_api/archive_metadata.json             | Yes        | a960c6e46dde87b7de95ef8a7aecefd7f1216d9bd02fcc8e1ee4285f4a14d659 | a960c6e46dde87b7de95ef8a7aecefd7f1216d9bd02fcc8e1ee4285f4a14d659 | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `archive_metadata.json`.             |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/153908_odds_api/provider_run_report.json          | Yes        | cb8882d430bb3bea56f75705d4cf2c59443e656350d23d833c920ce4a645908a | cb8882d430bb3bea56f75705d4cf2c59443e656350d23d833c920ce4a645908a | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_run_report.json`.          |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/153908_odds_api/provider_run_report.md            | Yes        | 58dd62e80369e1b6c8f836c488fb3bff15561724523b62cf77a0c3c4100b8a95 | 58dd62e80369e1b6c8f836c488fb3bff15561724523b62cf77a0c3c4100b8a95 | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_run_report.md`.            |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/153908_odds_api/provider_shadow_verification.csv  | Yes        | 3474512ebc0b8ed461ebfbfbc74791e4bed3f4d0db41df17ad8a54ded1923422 | 3474512ebc0b8ed461ebfbfbc74791e4bed3f4d0db41df17ad8a54ded1923422 | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_shadow_verification.csv`.  |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/153908_odds_api/provider_shadow_verification.json | Yes        | 86d1d3c4aa165a282e60bb1f7c569c188d385f9ea9ab8de83564e81d3a3e9b5c | 86d1d3c4aa165a282e60bb1f7c569c188d385f9ea9ab8de83564e81d3a3e9b5c | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_shadow_verification.json`. |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/153908_odds_api/provider_shadow_verification.md   | Yes        | 9d3ba1d0f3d1272d37b5ebc4ed918fd2e03e4752a065b8968e22ca3b192e28ab | 9d3ba1d0f3d1272d37b5ebc4ed918fd2e03e4752a065b8968e22ca3b192e28ab | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_shadow_verification.md`.   |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/153908_odds_api/staging_input_validation.csv      | Yes        | 7df1af4bd9314f2d585e4e1512236957cca48076610127b2f9fb47379a046bb0 | 7df1af4bd9314f2d585e4e1512236957cca48076610127b2f9fb47379a046bb0 | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `staging_input_validation.csv`.      |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/153908_odds_api/staging_input_validation.json     | Yes        | 362d12f239d270df4011572a035fcfb6a50825c33559629691de3d9339ea077b | 362d12f239d270df4011572a035fcfb6a50825c33559629691de3d9339ea077b | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `staging_input_validation.json`.     |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/153908_odds_api/staging_input_validation.md       | Yes        | 0ec7265f967d329b1d02a8c59e483a159a3f3cf0e4b5ced2ee533b13360673aa | 0ec7265f967d329b1d02a8c59e483a159a3f3cf0e4b5ced2ee533b13360673aa | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `staging_input_validation.md`.       |
| reviewed_shadow_archive_bundle                 | data/outputs/archive/provider_shadow_runs/2026-08-21/153816_odds_api                                   | Yes        | 30f6c1ad63ccda5181ff5fd39a9f9f474e6f0630041d22b3c84b37cd4b564491 | 30f6c1ad63ccda5181ff5fd39a9f9f474e6f0630041d22b3c84b37cd4b564491 | Included | Shadow ready for review          | 2026-08-21T15:38:16+00:00 | Current checksum matches every available binding. Archive contains 9 file(s).                                 |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/153816_odds_api/archive_metadata.json             | Yes        | de53269f32536f3ddd216d10630266cdfdb4be7846d7fc8763fb4aeb2578ab2b | de53269f32536f3ddd216d10630266cdfdb4be7846d7fc8763fb4aeb2578ab2b | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `archive_metadata.json`.             |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/153816_odds_api/provider_run_report.json          | Yes        | 75364bae70db3dc0796cac51f3d4bf064e721052c5a82fc0c8986032055f4aa4 | 75364bae70db3dc0796cac51f3d4bf064e721052c5a82fc0c8986032055f4aa4 | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_run_report.json`.          |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/153816_odds_api/provider_run_report.md            | Yes        | dfcb4c9b3fa5eec1b9a772e58f0535398362270f79e502df34eb7ed97575e28d | dfcb4c9b3fa5eec1b9a772e58f0535398362270f79e502df34eb7ed97575e28d | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_run_report.md`.            |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/153816_odds_api/provider_shadow_verification.csv  | Yes        | 707d720843d8482ed27cb57c491174476d905e3aea61adbcea798ebee626c62d | 707d720843d8482ed27cb57c491174476d905e3aea61adbcea798ebee626c62d | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_shadow_verification.csv`.  |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/153816_odds_api/provider_shadow_verification.json | Yes        | 7f5f2b304c2de115dfdc6bef98857998afdf95650e3ad9e7820a2ad8fe7a1e92 | 7f5f2b304c2de115dfdc6bef98857998afdf95650e3ad9e7820a2ad8fe7a1e92 | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_shadow_verification.json`. |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/153816_odds_api/provider_shadow_verification.md   | Yes        | 5c420d25c8410bb71eb993de630a1608befd25de221d8645a04a57d56d1a371b | 5c420d25c8410bb71eb993de630a1608befd25de221d8645a04a57d56d1a371b | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_shadow_verification.md`.   |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/153816_odds_api/staging_input_validation.csv      | Yes        | 7df1af4bd9314f2d585e4e1512236957cca48076610127b2f9fb47379a046bb0 | 7df1af4bd9314f2d585e4e1512236957cca48076610127b2f9fb47379a046bb0 | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `staging_input_validation.csv`.      |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/153816_odds_api/staging_input_validation.json     | Yes        | 2068165022d55730f2ddc30b9aead7bacc9a7202d606558098f9fd18b09f158b | 2068165022d55730f2ddc30b9aead7bacc9a7202d606558098f9fd18b09f158b | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `staging_input_validation.json`.     |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-21/153816_odds_api/staging_input_validation.md       | Yes        | fe0fe67740680c5a65e26f858d809f10362112515fbed751bb96f862293958dc | fe0fe67740680c5a65e26f858d809f10362112515fbed751bb96f862293958dc | Included |                                  |                           | Current checksum matches every available binding. Archive-relative path: `staging_input_validation.md`.       |
| provider_shadow_run_comparison                 | data/outputs/provider_shadow_run_comparison.json                                                       | Yes        | 81a23e87f4e585b8b1e7b3d25d80a5ad6ff7427f806563d98e22dff2785474e5 | 81a23e87f4e585b8b1e7b3d25d80a5ad6ff7427f806563d98e22dff2785474e5 | Included | Stable enough for review         | 2026-08-21T11:44:26-04:00 | Current checksum matches every available binding.                                                             |
| provider_allowlist_pr_conformance              | data/outputs/provider_allowlist_pr_conformance.json                                                    | No         |                                                                  | 12a7ad632267a72890884726f766466ccbe310690ed11542f918bdc57709c4f6 | Included | Conforms to preview              | 2026-08-21T11:54:40-04:00 | Current checksum matches every available binding.                                                             |
| staging_provider_policy                        | data/manual/staging_provider_policy.json                                                               | Yes        | fbd1a7cbe99930f1c1cde5286ed0149202d619f946324a0b5d31542d85264c9b | fbd1a7cbe99930f1c1cde5286ed0149202d619f946324a0b5d31542d85264c9b | Included |                                  |                           | Current checksum matches every available binding.                                                             |

## Checksum manifest

```json
[
  {
    "checksum_sha256": "fbd1a7cbe99930f1c1cde5286ed0149202d619f946324a0b5d31542d85264c9b",
    "path": "data/manual/staging_provider_policy.json"
  },
  {
    "checksum_sha256": "30f6c1ad63ccda5181ff5fd39a9f9f474e6f0630041d22b3c84b37cd4b564491",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/153816_odds_api"
  },
  {
    "checksum_sha256": "de53269f32536f3ddd216d10630266cdfdb4be7846d7fc8763fb4aeb2578ab2b",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/153816_odds_api/archive_metadata.json"
  },
  {
    "checksum_sha256": "75364bae70db3dc0796cac51f3d4bf064e721052c5a82fc0c8986032055f4aa4",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/153816_odds_api/provider_run_report.json"
  },
  {
    "checksum_sha256": "dfcb4c9b3fa5eec1b9a772e58f0535398362270f79e502df34eb7ed97575e28d",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/153816_odds_api/provider_run_report.md"
  },
  {
    "checksum_sha256": "707d720843d8482ed27cb57c491174476d905e3aea61adbcea798ebee626c62d",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/153816_odds_api/provider_shadow_verification.csv"
  },
  {
    "checksum_sha256": "7f5f2b304c2de115dfdc6bef98857998afdf95650e3ad9e7820a2ad8fe7a1e92",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/153816_odds_api/provider_shadow_verification.json"
  },
  {
    "checksum_sha256": "5c420d25c8410bb71eb993de630a1608befd25de221d8645a04a57d56d1a371b",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/153816_odds_api/provider_shadow_verification.md"
  },
  {
    "checksum_sha256": "7df1af4bd9314f2d585e4e1512236957cca48076610127b2f9fb47379a046bb0",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/153816_odds_api/staging_input_validation.csv"
  },
  {
    "checksum_sha256": "2068165022d55730f2ddc30b9aead7bacc9a7202d606558098f9fd18b09f158b",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/153816_odds_api/staging_input_validation.json"
  },
  {
    "checksum_sha256": "fe0fe67740680c5a65e26f858d809f10362112515fbed751bb96f862293958dc",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/153816_odds_api/staging_input_validation.md"
  },
  {
    "checksum_sha256": "0e0aae3c2da51bf78bd25991ad100e5421195356ff9f3fa8bc2c8c1bae411398",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/153908_odds_api"
  },
  {
    "checksum_sha256": "a960c6e46dde87b7de95ef8a7aecefd7f1216d9bd02fcc8e1ee4285f4a14d659",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/153908_odds_api/archive_metadata.json"
  },
  {
    "checksum_sha256": "cb8882d430bb3bea56f75705d4cf2c59443e656350d23d833c920ce4a645908a",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/153908_odds_api/provider_run_report.json"
  },
  {
    "checksum_sha256": "58dd62e80369e1b6c8f836c488fb3bff15561724523b62cf77a0c3c4100b8a95",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/153908_odds_api/provider_run_report.md"
  },
  {
    "checksum_sha256": "3474512ebc0b8ed461ebfbfbc74791e4bed3f4d0db41df17ad8a54ded1923422",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/153908_odds_api/provider_shadow_verification.csv"
  },
  {
    "checksum_sha256": "86d1d3c4aa165a282e60bb1f7c569c188d385f9ea9ab8de83564e81d3a3e9b5c",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/153908_odds_api/provider_shadow_verification.json"
  },
  {
    "checksum_sha256": "9d3ba1d0f3d1272d37b5ebc4ed918fd2e03e4752a065b8968e22ca3b192e28ab",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/153908_odds_api/provider_shadow_verification.md"
  },
  {
    "checksum_sha256": "7df1af4bd9314f2d585e4e1512236957cca48076610127b2f9fb47379a046bb0",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/153908_odds_api/staging_input_validation.csv"
  },
  {
    "checksum_sha256": "362d12f239d270df4011572a035fcfb6a50825c33559629691de3d9339ea077b",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/153908_odds_api/staging_input_validation.json"
  },
  {
    "checksum_sha256": "0ec7265f967d329b1d02a8c59e483a159a3f3cf0e4b5ced2ee533b13360673aa",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/153908_odds_api/staging_input_validation.md"
  },
  {
    "checksum_sha256": "9525c7de23a88ac19b34b9e812e68b6caa156d5d3483f9360b12edfc3c262935",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/154019_odds_api"
  },
  {
    "checksum_sha256": "74ab893d1efbde34329b9df97b82803e14967b7e326c519d4f7526b9be2c7038",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/154019_odds_api/archive_metadata.json"
  },
  {
    "checksum_sha256": "4536fcca99fe06c8f911231ca49dbd0bcf0ee18983c495d33e782a572dc601d6",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/154019_odds_api/provider_run_report.json"
  },
  {
    "checksum_sha256": "527c90d02e1be6b126fa3cd7987ae23097e0b3e067eaf762e3275651a09ae76d",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/154019_odds_api/provider_run_report.md"
  },
  {
    "checksum_sha256": "d4c9aa228517a4b0487d82e131110d9bb426bdefa540cc895e36057f14ccd3f2",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/154019_odds_api/provider_shadow_verification.csv"
  },
  {
    "checksum_sha256": "73899e80687c4db501eeaed0a068ffd7dff943b7e0b18e0f7185ff1b685b847b",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/154019_odds_api/provider_shadow_verification.json"
  },
  {
    "checksum_sha256": "1d0e3b710dfddb0b0e26cf9e05e14fd83eb4d4be17cfe7bb98d4ecb20f3d04f8",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/154019_odds_api/provider_shadow_verification.md"
  },
  {
    "checksum_sha256": "7df1af4bd9314f2d585e4e1512236957cca48076610127b2f9fb47379a046bb0",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/154019_odds_api/staging_input_validation.csv"
  },
  {
    "checksum_sha256": "b68af8ad108e0706f1c10c20371c6bbd3ad4f01975b9c8d57406728813c3e08f",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/154019_odds_api/staging_input_validation.json"
  },
  {
    "checksum_sha256": "ee039aa0ed52cd8f0e8be3efb1e0c163e34a10f8f0e0d2eb9f0b48ecdfa02518",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/154019_odds_api/staging_input_validation.md"
  },
  {
    "checksum_sha256": "539a2672fc06e78616e8235fecd39d85a9c67d697350547a6a20f80d0c197c28",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/154222_odds_api"
  },
  {
    "checksum_sha256": "e4a87d50ebc2f7cb5747c10b364363135f30c0c387b203f29ce389d215c5c117",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/154222_odds_api/archive_metadata.json"
  },
  {
    "checksum_sha256": "b3695687f7cf887af4234784d106698e11ccefa98e342425640d0cdced1d5ff5",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/154222_odds_api/provider_run_report.json"
  },
  {
    "checksum_sha256": "011c5d2360df796195efa3bbd82fa5a805baaeb570d6cc79e24d335ad3c79741",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/154222_odds_api/provider_run_report.md"
  },
  {
    "checksum_sha256": "148f77319e90180102c53481c663ac11d88e00f35da708e6f158116b599775e8",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/154222_odds_api/provider_shadow_verification.csv"
  },
  {
    "checksum_sha256": "9a0413dfe47a92e0178178c86f186205e67d5c1341a2ee0f28f96ec5810d5c99",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/154222_odds_api/provider_shadow_verification.json"
  },
  {
    "checksum_sha256": "1c5fda77240e8f0ed68938927c1ace8cb9396c8d39cc182cb34a0e0c6ae34e48",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/154222_odds_api/provider_shadow_verification.md"
  },
  {
    "checksum_sha256": "7df1af4bd9314f2d585e4e1512236957cca48076610127b2f9fb47379a046bb0",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/154222_odds_api/staging_input_validation.csv"
  },
  {
    "checksum_sha256": "75def9eb58b441c87aeebc5fa03b12a5118428dc809f559c7cd48645987feeaf",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/154222_odds_api/staging_input_validation.json"
  },
  {
    "checksum_sha256": "68e866e730e1df7e8db1e507ce0319d16473d902fe585fa2344f7cf5a24c509a",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/154222_odds_api/staging_input_validation.md"
  },
  {
    "checksum_sha256": "6b2842cbc84eddbecbd3ca435a652bc900f47c2b00999985ce398c47059aa866",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/154335_odds_api"
  },
  {
    "checksum_sha256": "00a8ed2f5e471c240b7333af072afdb4d96ff2bbb3737c3dc661977a52d6f9cc",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/154335_odds_api/archive_metadata.json"
  },
  {
    "checksum_sha256": "bef6bd5c9af16226774580da6b204d1cedf055d27834b4241b985d45a747a892",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/154335_odds_api/provider_run_report.json"
  },
  {
    "checksum_sha256": "e58ae4ab3612cbde9043de6445d4b6f24bf1124d5db4e350377ea14b793b2b1a",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/154335_odds_api/provider_run_report.md"
  },
  {
    "checksum_sha256": "df25ef586a3eb596e5003ee6dce8b1b4decf509876dd5bd8864bb0988167aba4",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/154335_odds_api/provider_shadow_verification.csv"
  },
  {
    "checksum_sha256": "e9afa9b87bbbab56915eb2fa336d611975ce7ed81dbdb26777698d947085ead9",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/154335_odds_api/provider_shadow_verification.json"
  },
  {
    "checksum_sha256": "478ed0325f094cc5e97e24cb20d0e872183396a2a3d357bc279bb84da9754b2d",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/154335_odds_api/provider_shadow_verification.md"
  },
  {
    "checksum_sha256": "7df1af4bd9314f2d585e4e1512236957cca48076610127b2f9fb47379a046bb0",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/154335_odds_api/staging_input_validation.csv"
  },
  {
    "checksum_sha256": "6b06bae57bcdb61f2296012ed70453b20fac85c822136130f129a71d37a3075d",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/154335_odds_api/staging_input_validation.json"
  },
  {
    "checksum_sha256": "ba53f53f5554ca9a5387018b1f48a02d15cffb97b6075187289e196c2cace9f5",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-21/154335_odds_api/staging_input_validation.md"
  },
  {
    "checksum_sha256": "865d4e6ec1c4d1535a96966bba04df89ce3a0643e288cde36a3c5b643aac4b69",
    "path": "data/outputs/provider_acceptance_checklist.json"
  },
  {
    "checksum_sha256": "12a7ad632267a72890884726f766466ccbe310690ed11542f918bdc57709c4f6",
    "path": "data/outputs/provider_allowlist_pr_conformance.json"
  },
  {
    "checksum_sha256": "a5c7969546abfa8fedecb0359017e6c29e73362fc888740a2480d94e7895322f",
    "path": "data/outputs/provider_allowlist_pr_preview.json"
  },
  {
    "checksum_sha256": "5ffec591e5ade9f3d74130b81e7ca7ebafdba5539b17fef758ad630291c81836",
    "path": "data/outputs/provider_human_acceptance_receipt.json"
  },
  {
    "checksum_sha256": "a5b59887648b80bd03f4ee8e04d7e6f68281497a7e18d3beac80bb77fc3a51fd",
    "path": "data/outputs/provider_human_acceptance_receipt_verification.json"
  },
  {
    "checksum_sha256": "81a23e87f4e585b8b1e7b3d25d80a5ad6ff7427f806563d98e22dff2785474e5",
    "path": "data/outputs/provider_shadow_run_comparison.json"
  }
]
```

## Recommended provider allowlist PR

- Title: Update the the_odds_api allowlisted market scope
- Description:

Updates the reviewed allowlist entry for `the_odds_api` (`odds_api`) to cover 1x2, total_2_5, btts, double_chance, draw_no_bet, corners_1x2, corners_total_9_5, corners_total_10_5. Binds the policy entry to human acceptance receipt `odds_api-20260821T114655-0400-20ffa5677988` and its verified evidence. Known limitations: Allowlisting does not bypass staging validation, freshness, completeness, checksum, receipt, or Thursday cutoff gates. This policy-only proposal does not promote staging, run a provider, generate picks, place bets, or enable cron.

## Decision boundary

A ready bundle proves which evidence bytes were reviewed; it does not make the policy change. Provider allowlisting remains a separate PR, and cron remains disabled until a later independent review explicitly enables it.