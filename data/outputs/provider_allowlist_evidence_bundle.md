# Provider Allowlist PR Evidence Bundle

**Nothing was applied.** This checksum-bound report only gathers and verifies existing review evidence. It does not edit provider policy, allowlist a provider, promote staging, run providers, generate picks, place bets, or enable cron.

## Bundle verdict

- **Evidence bundle ready for PR review**
- Provider: **the_odds_api** (`odds_api`)
- Bundle ID: `odds_api-allowlist-evidence-8b66627b1081c104`
- Bundle SHA-256: `8b66627b1081c1044e0ae0efffc450f8bd7be4332f58e93a692a3f97a69866bf`
- Included checksum entries: **56**

## Review decisions

- Preview verdict: **Ready for separate allowlist PR**
- Conformance verdict: **Not applicable**
- Receipt verification verdict: **Verified for allowlist PR review**
- Human receipt ID: `odds_api-20260817T155217-0400-8204291a2b19`
- Checklist verdict: **Ready for human allowlist review**

## Included evidence and status

| evidence_type                                  | evidence_path                                                                                          | required   | expected_checksum_sha256                                         | current_checksum_sha256                                          | status         | verdict                          | generated_at              | details                                                                                                       |
|:-----------------------------------------------|:-------------------------------------------------------------------------------------------------------|:-----------|:-----------------------------------------------------------------|:-----------------------------------------------------------------|:---------------|:---------------------------------|:--------------------------|:--------------------------------------------------------------------------------------------------------------|
| provider_allowlist_pr_preview                  | data/outputs/provider_allowlist_pr_preview.json                                                        | Yes        |                                                                  | 281ecfb181959f98dfc9a7dd0b2bce3b769348ec3a1f033cab6c87306fa3197d | Included       | Ready for separate allowlist PR  | 2026-08-17T15:52:18-04:00 | Current checksum matches every available binding.                                                             |
| provider_human_acceptance_receipt_verification | data/outputs/provider_human_acceptance_receipt_verification.json                                       | Yes        | 837ec2d2bb6b0796a66f1714f3168c9f971256b5221d78602bbe1690498a77ee | 837ec2d2bb6b0796a66f1714f3168c9f971256b5221d78602bbe1690498a77ee | Included       | Verified for allowlist PR review | 2026-08-17T15:52:18-04:00 | Current checksum matches every available binding.                                                             |
| provider_human_acceptance_receipt              | data/outputs/provider_human_acceptance_receipt.json                                                    | Yes        | 635160dd9f1c6496288695e87ad876ac5362d8d27faf874a78de8bd4d111a17e | 635160dd9f1c6496288695e87ad876ac5362d8d27faf874a78de8bd4d111a17e | Included       | approved_for_allowlist_pr        |                           | Current checksum matches every available binding.                                                             |
| provider_acceptance_checklist                  | data/outputs/provider_acceptance_checklist.json                                                        | Yes        | 7aa6af6017dcf0b243fa43add16307df4877d77f8b079aa0d9ac9e324331dd98 | 7aa6af6017dcf0b243fa43add16307df4877d77f8b079aa0d9ac9e324331dd98 | Included       | Ready for human allowlist review | 2026-08-17T15:17:20-04:00 | Current checksum matches every available binding.                                                             |
| reviewed_shadow_archive_bundle                 | data/outputs/archive/provider_shadow_runs/2026-08-17/151717_odds_api                                   | Yes        | 350e8968939101ed4f96b65b40abea897318695fc14494007cbcaa7d5065af96 | 350e8968939101ed4f96b65b40abea897318695fc14494007cbcaa7d5065af96 | Included       | Needs provider policy review     | 2026-08-17T15:17:17-04:00 | Current checksum matches every available binding. Archive contains 9 file(s).                                 |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151717_odds_api/archive_metadata.json             | Yes        | 3fcfd33f2651d126856db4512df948fe6f15efe4599bf22bfb95cb2a428dcf4c | 3fcfd33f2651d126856db4512df948fe6f15efe4599bf22bfb95cb2a428dcf4c | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `archive_metadata.json`.             |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151717_odds_api/provider_run_report.json          | Yes        | edc6920d452993f45be07a544e102b91fb52bcfbaa7aaf982dfd681b3cd1f0d6 | edc6920d452993f45be07a544e102b91fb52bcfbaa7aaf982dfd681b3cd1f0d6 | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_run_report.json`.          |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151717_odds_api/provider_run_report.md            | Yes        | 195d29de8c73ceb732d5a26202d98e04b575a05c2c4e77c1cdf907208122fba5 | 195d29de8c73ceb732d5a26202d98e04b575a05c2c4e77c1cdf907208122fba5 | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_run_report.md`.            |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151717_odds_api/provider_shadow_verification.csv  | Yes        | 62e51728106c3ac4d49540a778b7f79907626497c9bc1ad5da865247259bb20a | 62e51728106c3ac4d49540a778b7f79907626497c9bc1ad5da865247259bb20a | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_shadow_verification.csv`.  |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151717_odds_api/provider_shadow_verification.json | Yes        | d65e661b2a8ca1026a1a74b141ec42f9a474bcba786d1c688a15c7cae7e1596e | d65e661b2a8ca1026a1a74b141ec42f9a474bcba786d1c688a15c7cae7e1596e | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_shadow_verification.json`. |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151717_odds_api/provider_shadow_verification.md   | Yes        | cdb2bed16160010360d798f22a4bd93bf3a9a3806e1464f65bd70f904eeba778 | cdb2bed16160010360d798f22a4bd93bf3a9a3806e1464f65bd70f904eeba778 | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_shadow_verification.md`.   |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151717_odds_api/staging_input_validation.csv      | Yes        | 71d1a3db372bfd2642e5b9220140f408961a48219d651baf4e4ca36992b0e58b | 71d1a3db372bfd2642e5b9220140f408961a48219d651baf4e4ca36992b0e58b | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `staging_input_validation.csv`.      |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151717_odds_api/staging_input_validation.json     | Yes        | 8eb55a00a7d1bdfda4953f3fc9c63dc2c249b3dfcfafd929dc3a07071545e384 | 8eb55a00a7d1bdfda4953f3fc9c63dc2c249b3dfcfafd929dc3a07071545e384 | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `staging_input_validation.json`.     |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151717_odds_api/staging_input_validation.md       | Yes        | 533ac8a16c5642dc7d0c8238973b912156d4082743c0fad3f783146bd526c2b8 | 533ac8a16c5642dc7d0c8238973b912156d4082743c0fad3f783146bd526c2b8 | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `staging_input_validation.md`.       |
| reviewed_shadow_archive_bundle                 | data/outputs/archive/provider_shadow_runs/2026-08-17/151711_odds_api                                   | Yes        | 9548e60f62463182766da19fabfb5228a473fe395bc167abea691aad335fd735 | 9548e60f62463182766da19fabfb5228a473fe395bc167abea691aad335fd735 | Included       | Needs provider policy review     | 2026-08-17T15:17:11-04:00 | Current checksum matches every available binding. Archive contains 9 file(s).                                 |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151711_odds_api/archive_metadata.json             | Yes        | 410652f1d2d5ec77a9088fd4e18710b58441b9de34bdaaca78c364ec2cf3d8a4 | 410652f1d2d5ec77a9088fd4e18710b58441b9de34bdaaca78c364ec2cf3d8a4 | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `archive_metadata.json`.             |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151711_odds_api/provider_run_report.json          | Yes        | acbd4345152736fbaa8390d4a3d043aefd23136ca9a820e08b7f74a8a4d7e85b | acbd4345152736fbaa8390d4a3d043aefd23136ca9a820e08b7f74a8a4d7e85b | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_run_report.json`.          |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151711_odds_api/provider_run_report.md            | Yes        | 66a4786a4efcbd1d756638a8b77cf5fecfe79372538f9bc881172a82ea3dc44e | 66a4786a4efcbd1d756638a8b77cf5fecfe79372538f9bc881172a82ea3dc44e | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_run_report.md`.            |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151711_odds_api/provider_shadow_verification.csv  | Yes        | d4ea201876fc3d76131a492adb2fca0fbf025d5433b666d07306f908e9b9a7ac | d4ea201876fc3d76131a492adb2fca0fbf025d5433b666d07306f908e9b9a7ac | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_shadow_verification.csv`.  |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151711_odds_api/provider_shadow_verification.json | Yes        | 66dd3d01707ad2d74a84569d6ad84c1835da4750acc0c43ffaa49d167a2673b6 | 66dd3d01707ad2d74a84569d6ad84c1835da4750acc0c43ffaa49d167a2673b6 | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_shadow_verification.json`. |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151711_odds_api/provider_shadow_verification.md   | Yes        | 9177c85c2b1484e40aaa80b2c44d4c11558cca0ce4715b8c78015a328c4b052b | 9177c85c2b1484e40aaa80b2c44d4c11558cca0ce4715b8c78015a328c4b052b | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_shadow_verification.md`.   |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151711_odds_api/staging_input_validation.csv      | Yes        | 71d1a3db372bfd2642e5b9220140f408961a48219d651baf4e4ca36992b0e58b | 71d1a3db372bfd2642e5b9220140f408961a48219d651baf4e4ca36992b0e58b | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `staging_input_validation.csv`.      |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151711_odds_api/staging_input_validation.json     | Yes        | 1c90e8941bf13ac58e118fc32e681ec097b65f130f341dcd503a0944d73760a9 | 1c90e8941bf13ac58e118fc32e681ec097b65f130f341dcd503a0944d73760a9 | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `staging_input_validation.json`.     |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151711_odds_api/staging_input_validation.md       | Yes        | bf0d62516bfb1438a32c4af7a7dbfc21a7eb418f15641ea4f8b1f205033039d0 | bf0d62516bfb1438a32c4af7a7dbfc21a7eb418f15641ea4f8b1f205033039d0 | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `staging_input_validation.md`.       |
| reviewed_shadow_archive_bundle                 | data/outputs/archive/provider_shadow_runs/2026-08-17/151706_odds_api                                   | Yes        | 03e810ba7a46d193774e99f05e8f67cf21dfae96caa64b767577a951377c50df | 03e810ba7a46d193774e99f05e8f67cf21dfae96caa64b767577a951377c50df | Included       | Needs provider policy review     | 2026-08-17T15:17:06-04:00 | Current checksum matches every available binding. Archive contains 9 file(s).                                 |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151706_odds_api/archive_metadata.json             | Yes        | f80f7e619ceee625685a2834b57e2270476abfc022b97562d833432ec5ee8ca5 | f80f7e619ceee625685a2834b57e2270476abfc022b97562d833432ec5ee8ca5 | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `archive_metadata.json`.             |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151706_odds_api/provider_run_report.json          | Yes        | 4b6b6bda632f1b579b547fb46fb87c08414059d35b90cba0f1c4c616e5cd6a67 | 4b6b6bda632f1b579b547fb46fb87c08414059d35b90cba0f1c4c616e5cd6a67 | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_run_report.json`.          |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151706_odds_api/provider_run_report.md            | Yes        | ec6fc844dd335d99ce2d8e4b4478280b0e34a48f7c2185ac4da9ccad607ab802 | ec6fc844dd335d99ce2d8e4b4478280b0e34a48f7c2185ac4da9ccad607ab802 | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_run_report.md`.            |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151706_odds_api/provider_shadow_verification.csv  | Yes        | 5c158aef901de135a6f2e470e7c250b51ad49b6ffed4081d125f6f93bf610837 | 5c158aef901de135a6f2e470e7c250b51ad49b6ffed4081d125f6f93bf610837 | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_shadow_verification.csv`.  |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151706_odds_api/provider_shadow_verification.json | Yes        | 31b00589a20da8f8f81ce1ef88ed55368fc83d71ca8bca84d30703a02e7e1131 | 31b00589a20da8f8f81ce1ef88ed55368fc83d71ca8bca84d30703a02e7e1131 | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_shadow_verification.json`. |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151706_odds_api/provider_shadow_verification.md   | Yes        | 4de53aafaf77407750de196d2f54852aab06cca939a0ade86843a7314ed2b6b7 | 4de53aafaf77407750de196d2f54852aab06cca939a0ade86843a7314ed2b6b7 | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_shadow_verification.md`.   |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151706_odds_api/staging_input_validation.csv      | Yes        | 71d1a3db372bfd2642e5b9220140f408961a48219d651baf4e4ca36992b0e58b | 71d1a3db372bfd2642e5b9220140f408961a48219d651baf4e4ca36992b0e58b | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `staging_input_validation.csv`.      |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151706_odds_api/staging_input_validation.json     | Yes        | 784197ca738fc3c7b10b77a256e5b0f7330b274069343549a3b15990047efa6b | 784197ca738fc3c7b10b77a256e5b0f7330b274069343549a3b15990047efa6b | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `staging_input_validation.json`.     |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151706_odds_api/staging_input_validation.md       | Yes        | 387663c7c7da7e9449edb06fb3b98e48fcc86fc70bd29210774f966b07e543bc | 387663c7c7da7e9449edb06fb3b98e48fcc86fc70bd29210774f966b07e543bc | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `staging_input_validation.md`.       |
| reviewed_shadow_archive_bundle                 | data/outputs/archive/provider_shadow_runs/2026-08-17/151700_odds_api                                   | Yes        | 1fd4711908ca3ccc01d0144ef30064250bddb1ba9de18877ea9222e1aa14e760 | 1fd4711908ca3ccc01d0144ef30064250bddb1ba9de18877ea9222e1aa14e760 | Included       | Needs provider policy review     | 2026-08-17T15:17:00-04:00 | Current checksum matches every available binding. Archive contains 9 file(s).                                 |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151700_odds_api/archive_metadata.json             | Yes        | 55781d1f8de48409c7d2471280e9d6f9fe54de087f1ca26d18c4ff7a4f61fd20 | 55781d1f8de48409c7d2471280e9d6f9fe54de087f1ca26d18c4ff7a4f61fd20 | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `archive_metadata.json`.             |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151700_odds_api/provider_run_report.json          | Yes        | 95ec757b729820f96988aec16eba7dc6a0c167161ac6b2d87f8ce5de1258a23f | 95ec757b729820f96988aec16eba7dc6a0c167161ac6b2d87f8ce5de1258a23f | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_run_report.json`.          |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151700_odds_api/provider_run_report.md            | Yes        | 138f77d3bf7e6e9e1f2a5f32dce344595e9e248adf0a65c4080eb3493f4d3b69 | 138f77d3bf7e6e9e1f2a5f32dce344595e9e248adf0a65c4080eb3493f4d3b69 | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_run_report.md`.            |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151700_odds_api/provider_shadow_verification.csv  | Yes        | b327aff68b797eab55f069e651b75fa09173fdf3a3faeeaeb2b94cfdcb543425 | b327aff68b797eab55f069e651b75fa09173fdf3a3faeeaeb2b94cfdcb543425 | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_shadow_verification.csv`.  |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151700_odds_api/provider_shadow_verification.json | Yes        | 60c8800bc4c3991806a376500adccb6fa1b51fea9a8841d8cfa1da47ef914c2d | 60c8800bc4c3991806a376500adccb6fa1b51fea9a8841d8cfa1da47ef914c2d | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_shadow_verification.json`. |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151700_odds_api/provider_shadow_verification.md   | Yes        | 165cf94f22c3e7e0260f6c1070aa188793197b19ccd4602455bb62d5645fcfb2 | 165cf94f22c3e7e0260f6c1070aa188793197b19ccd4602455bb62d5645fcfb2 | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_shadow_verification.md`.   |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151700_odds_api/staging_input_validation.csv      | Yes        | 71d1a3db372bfd2642e5b9220140f408961a48219d651baf4e4ca36992b0e58b | 71d1a3db372bfd2642e5b9220140f408961a48219d651baf4e4ca36992b0e58b | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `staging_input_validation.csv`.      |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151700_odds_api/staging_input_validation.json     | Yes        | 353abbdaf7db30276d8a55be413bea584c00c77a3adfffa8b25b4b113769acdf | 353abbdaf7db30276d8a55be413bea584c00c77a3adfffa8b25b4b113769acdf | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `staging_input_validation.json`.     |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151700_odds_api/staging_input_validation.md       | Yes        | ad944349776111199b46f48da66000498b7e9ba8a4b4ed793b45803bbd5a8faa | ad944349776111199b46f48da66000498b7e9ba8a4b4ed793b45803bbd5a8faa | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `staging_input_validation.md`.       |
| reviewed_shadow_archive_bundle                 | data/outputs/archive/provider_shadow_runs/2026-08-17/151655_odds_api                                   | Yes        | 68478b7192e7004b4e7426223e39e06d7074b3704681c5072409669ec9432471 | 68478b7192e7004b4e7426223e39e06d7074b3704681c5072409669ec9432471 | Included       | Needs provider policy review     | 2026-08-17T15:16:55-04:00 | Current checksum matches every available binding. Archive contains 9 file(s).                                 |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151655_odds_api/archive_metadata.json             | Yes        | 684562bde7e3fc35d21fb7f5c1c1da47af288c3afe8ba1a7caab1842cdc6e21c | 684562bde7e3fc35d21fb7f5c1c1da47af288c3afe8ba1a7caab1842cdc6e21c | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `archive_metadata.json`.             |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151655_odds_api/provider_run_report.json          | Yes        | 7ad2f966ce928e2e8af1d34a143f4d89c94bc33501be2af7007989000b2788f6 | 7ad2f966ce928e2e8af1d34a143f4d89c94bc33501be2af7007989000b2788f6 | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_run_report.json`.          |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151655_odds_api/provider_run_report.md            | Yes        | 8127e840aa0595948c151b7e9e8bff5e4a1f994e9d613989f722ff79577c27e0 | 8127e840aa0595948c151b7e9e8bff5e4a1f994e9d613989f722ff79577c27e0 | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_run_report.md`.            |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151655_odds_api/provider_shadow_verification.csv  | Yes        | 36fa12d6a6ad907441cbce1e269479b95f8d56df98e949591ddc992a6bc65f2c | 36fa12d6a6ad907441cbce1e269479b95f8d56df98e949591ddc992a6bc65f2c | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_shadow_verification.csv`.  |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151655_odds_api/provider_shadow_verification.json | Yes        | ddd9ba1095c86b0a2bea83cb910206c752c1ccb3da0a9c583e21b2cb95461a2a | ddd9ba1095c86b0a2bea83cb910206c752c1ccb3da0a9c583e21b2cb95461a2a | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_shadow_verification.json`. |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151655_odds_api/provider_shadow_verification.md   | Yes        | 1e23a0d64dd1a90d5a132fd2ceca7111da87a2b00356acee053b70b1d6d7101a | 1e23a0d64dd1a90d5a132fd2ceca7111da87a2b00356acee053b70b1d6d7101a | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `provider_shadow_verification.md`.   |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151655_odds_api/staging_input_validation.csv      | Yes        | 71d1a3db372bfd2642e5b9220140f408961a48219d651baf4e4ca36992b0e58b | 71d1a3db372bfd2642e5b9220140f408961a48219d651baf4e4ca36992b0e58b | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `staging_input_validation.csv`.      |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151655_odds_api/staging_input_validation.json     | Yes        | cd7713ef411133db51550ef7f553db5b69347e52cb640e4d345d443febd5adfb | cd7713ef411133db51550ef7f553db5b69347e52cb640e4d345d443febd5adfb | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `staging_input_validation.json`.     |
| reviewed_shadow_archive_file                   | data/outputs/archive/provider_shadow_runs/2026-08-17/151655_odds_api/staging_input_validation.md       | Yes        | a3ac3f01b94fc9d3358d093b22828629acaec23cf247da421c32676764be1f72 | a3ac3f01b94fc9d3358d093b22828629acaec23cf247da421c32676764be1f72 | Included       |                                  |                           | Current checksum matches every available binding. Archive-relative path: `staging_input_validation.md`.       |
| provider_shadow_run_comparison                 | data/outputs/provider_shadow_run_comparison.json                                                       | Yes        | 17bd99391c54fcb732f1be6e4350b1cd2f30ec15b7dc32677e01299ca665211d | 17bd99391c54fcb732f1be6e4350b1cd2f30ec15b7dc32677e01299ca665211d | Included       | Stable enough for review         | 2026-08-17T15:51:40-04:00 | Current checksum matches every available binding.                                                             |
| provider_allowlist_pr_conformance              | data/outputs/provider_allowlist_pr_conformance.json                                                    | No         |                                                                  |                                                                  | Not applicable |                                  |                           | No policy change has been checked yet; conformance is optional before PR review.                              |
| staging_provider_policy                        | data/manual/staging_provider_policy.json                                                               | Yes        | 23d88241a66c9cc86b59d4278694b4e1522fd48048c268e0744dd217020b21d3 | 23d88241a66c9cc86b59d4278694b4e1522fd48048c268e0744dd217020b21d3 | Included       |                                  |                           | Current checksum matches every available binding.                                                             |

## Checksum manifest

```json
[
  {
    "checksum_sha256": "23d88241a66c9cc86b59d4278694b4e1522fd48048c268e0744dd217020b21d3",
    "path": "data/manual/staging_provider_policy.json"
  },
  {
    "checksum_sha256": "68478b7192e7004b4e7426223e39e06d7074b3704681c5072409669ec9432471",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151655_odds_api"
  },
  {
    "checksum_sha256": "684562bde7e3fc35d21fb7f5c1c1da47af288c3afe8ba1a7caab1842cdc6e21c",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151655_odds_api/archive_metadata.json"
  },
  {
    "checksum_sha256": "7ad2f966ce928e2e8af1d34a143f4d89c94bc33501be2af7007989000b2788f6",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151655_odds_api/provider_run_report.json"
  },
  {
    "checksum_sha256": "8127e840aa0595948c151b7e9e8bff5e4a1f994e9d613989f722ff79577c27e0",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151655_odds_api/provider_run_report.md"
  },
  {
    "checksum_sha256": "36fa12d6a6ad907441cbce1e269479b95f8d56df98e949591ddc992a6bc65f2c",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151655_odds_api/provider_shadow_verification.csv"
  },
  {
    "checksum_sha256": "ddd9ba1095c86b0a2bea83cb910206c752c1ccb3da0a9c583e21b2cb95461a2a",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151655_odds_api/provider_shadow_verification.json"
  },
  {
    "checksum_sha256": "1e23a0d64dd1a90d5a132fd2ceca7111da87a2b00356acee053b70b1d6d7101a",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151655_odds_api/provider_shadow_verification.md"
  },
  {
    "checksum_sha256": "71d1a3db372bfd2642e5b9220140f408961a48219d651baf4e4ca36992b0e58b",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151655_odds_api/staging_input_validation.csv"
  },
  {
    "checksum_sha256": "cd7713ef411133db51550ef7f553db5b69347e52cb640e4d345d443febd5adfb",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151655_odds_api/staging_input_validation.json"
  },
  {
    "checksum_sha256": "a3ac3f01b94fc9d3358d093b22828629acaec23cf247da421c32676764be1f72",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151655_odds_api/staging_input_validation.md"
  },
  {
    "checksum_sha256": "1fd4711908ca3ccc01d0144ef30064250bddb1ba9de18877ea9222e1aa14e760",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151700_odds_api"
  },
  {
    "checksum_sha256": "55781d1f8de48409c7d2471280e9d6f9fe54de087f1ca26d18c4ff7a4f61fd20",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151700_odds_api/archive_metadata.json"
  },
  {
    "checksum_sha256": "95ec757b729820f96988aec16eba7dc6a0c167161ac6b2d87f8ce5de1258a23f",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151700_odds_api/provider_run_report.json"
  },
  {
    "checksum_sha256": "138f77d3bf7e6e9e1f2a5f32dce344595e9e248adf0a65c4080eb3493f4d3b69",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151700_odds_api/provider_run_report.md"
  },
  {
    "checksum_sha256": "b327aff68b797eab55f069e651b75fa09173fdf3a3faeeaeb2b94cfdcb543425",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151700_odds_api/provider_shadow_verification.csv"
  },
  {
    "checksum_sha256": "60c8800bc4c3991806a376500adccb6fa1b51fea9a8841d8cfa1da47ef914c2d",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151700_odds_api/provider_shadow_verification.json"
  },
  {
    "checksum_sha256": "165cf94f22c3e7e0260f6c1070aa188793197b19ccd4602455bb62d5645fcfb2",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151700_odds_api/provider_shadow_verification.md"
  },
  {
    "checksum_sha256": "71d1a3db372bfd2642e5b9220140f408961a48219d651baf4e4ca36992b0e58b",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151700_odds_api/staging_input_validation.csv"
  },
  {
    "checksum_sha256": "353abbdaf7db30276d8a55be413bea584c00c77a3adfffa8b25b4b113769acdf",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151700_odds_api/staging_input_validation.json"
  },
  {
    "checksum_sha256": "ad944349776111199b46f48da66000498b7e9ba8a4b4ed793b45803bbd5a8faa",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151700_odds_api/staging_input_validation.md"
  },
  {
    "checksum_sha256": "03e810ba7a46d193774e99f05e8f67cf21dfae96caa64b767577a951377c50df",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151706_odds_api"
  },
  {
    "checksum_sha256": "f80f7e619ceee625685a2834b57e2270476abfc022b97562d833432ec5ee8ca5",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151706_odds_api/archive_metadata.json"
  },
  {
    "checksum_sha256": "4b6b6bda632f1b579b547fb46fb87c08414059d35b90cba0f1c4c616e5cd6a67",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151706_odds_api/provider_run_report.json"
  },
  {
    "checksum_sha256": "ec6fc844dd335d99ce2d8e4b4478280b0e34a48f7c2185ac4da9ccad607ab802",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151706_odds_api/provider_run_report.md"
  },
  {
    "checksum_sha256": "5c158aef901de135a6f2e470e7c250b51ad49b6ffed4081d125f6f93bf610837",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151706_odds_api/provider_shadow_verification.csv"
  },
  {
    "checksum_sha256": "31b00589a20da8f8f81ce1ef88ed55368fc83d71ca8bca84d30703a02e7e1131",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151706_odds_api/provider_shadow_verification.json"
  },
  {
    "checksum_sha256": "4de53aafaf77407750de196d2f54852aab06cca939a0ade86843a7314ed2b6b7",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151706_odds_api/provider_shadow_verification.md"
  },
  {
    "checksum_sha256": "71d1a3db372bfd2642e5b9220140f408961a48219d651baf4e4ca36992b0e58b",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151706_odds_api/staging_input_validation.csv"
  },
  {
    "checksum_sha256": "784197ca738fc3c7b10b77a256e5b0f7330b274069343549a3b15990047efa6b",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151706_odds_api/staging_input_validation.json"
  },
  {
    "checksum_sha256": "387663c7c7da7e9449edb06fb3b98e48fcc86fc70bd29210774f966b07e543bc",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151706_odds_api/staging_input_validation.md"
  },
  {
    "checksum_sha256": "9548e60f62463182766da19fabfb5228a473fe395bc167abea691aad335fd735",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151711_odds_api"
  },
  {
    "checksum_sha256": "410652f1d2d5ec77a9088fd4e18710b58441b9de34bdaaca78c364ec2cf3d8a4",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151711_odds_api/archive_metadata.json"
  },
  {
    "checksum_sha256": "acbd4345152736fbaa8390d4a3d043aefd23136ca9a820e08b7f74a8a4d7e85b",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151711_odds_api/provider_run_report.json"
  },
  {
    "checksum_sha256": "66a4786a4efcbd1d756638a8b77cf5fecfe79372538f9bc881172a82ea3dc44e",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151711_odds_api/provider_run_report.md"
  },
  {
    "checksum_sha256": "d4ea201876fc3d76131a492adb2fca0fbf025d5433b666d07306f908e9b9a7ac",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151711_odds_api/provider_shadow_verification.csv"
  },
  {
    "checksum_sha256": "66dd3d01707ad2d74a84569d6ad84c1835da4750acc0c43ffaa49d167a2673b6",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151711_odds_api/provider_shadow_verification.json"
  },
  {
    "checksum_sha256": "9177c85c2b1484e40aaa80b2c44d4c11558cca0ce4715b8c78015a328c4b052b",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151711_odds_api/provider_shadow_verification.md"
  },
  {
    "checksum_sha256": "71d1a3db372bfd2642e5b9220140f408961a48219d651baf4e4ca36992b0e58b",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151711_odds_api/staging_input_validation.csv"
  },
  {
    "checksum_sha256": "1c90e8941bf13ac58e118fc32e681ec097b65f130f341dcd503a0944d73760a9",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151711_odds_api/staging_input_validation.json"
  },
  {
    "checksum_sha256": "bf0d62516bfb1438a32c4af7a7dbfc21a7eb418f15641ea4f8b1f205033039d0",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151711_odds_api/staging_input_validation.md"
  },
  {
    "checksum_sha256": "350e8968939101ed4f96b65b40abea897318695fc14494007cbcaa7d5065af96",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151717_odds_api"
  },
  {
    "checksum_sha256": "3fcfd33f2651d126856db4512df948fe6f15efe4599bf22bfb95cb2a428dcf4c",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151717_odds_api/archive_metadata.json"
  },
  {
    "checksum_sha256": "edc6920d452993f45be07a544e102b91fb52bcfbaa7aaf982dfd681b3cd1f0d6",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151717_odds_api/provider_run_report.json"
  },
  {
    "checksum_sha256": "195d29de8c73ceb732d5a26202d98e04b575a05c2c4e77c1cdf907208122fba5",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151717_odds_api/provider_run_report.md"
  },
  {
    "checksum_sha256": "62e51728106c3ac4d49540a778b7f79907626497c9bc1ad5da865247259bb20a",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151717_odds_api/provider_shadow_verification.csv"
  },
  {
    "checksum_sha256": "d65e661b2a8ca1026a1a74b141ec42f9a474bcba786d1c688a15c7cae7e1596e",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151717_odds_api/provider_shadow_verification.json"
  },
  {
    "checksum_sha256": "cdb2bed16160010360d798f22a4bd93bf3a9a3806e1464f65bd70f904eeba778",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151717_odds_api/provider_shadow_verification.md"
  },
  {
    "checksum_sha256": "71d1a3db372bfd2642e5b9220140f408961a48219d651baf4e4ca36992b0e58b",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151717_odds_api/staging_input_validation.csv"
  },
  {
    "checksum_sha256": "8eb55a00a7d1bdfda4953f3fc9c63dc2c249b3dfcfafd929dc3a07071545e384",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151717_odds_api/staging_input_validation.json"
  },
  {
    "checksum_sha256": "533ac8a16c5642dc7d0c8238973b912156d4082743c0fad3f783146bd526c2b8",
    "path": "data/outputs/archive/provider_shadow_runs/2026-08-17/151717_odds_api/staging_input_validation.md"
  },
  {
    "checksum_sha256": "7aa6af6017dcf0b243fa43add16307df4877d77f8b079aa0d9ac9e324331dd98",
    "path": "data/outputs/provider_acceptance_checklist.json"
  },
  {
    "checksum_sha256": "281ecfb181959f98dfc9a7dd0b2bce3b769348ec3a1f033cab6c87306fa3197d",
    "path": "data/outputs/provider_allowlist_pr_preview.json"
  },
  {
    "checksum_sha256": "635160dd9f1c6496288695e87ad876ac5362d8d27faf874a78de8bd4d111a17e",
    "path": "data/outputs/provider_human_acceptance_receipt.json"
  },
  {
    "checksum_sha256": "837ec2d2bb6b0796a66f1714f3168c9f971256b5221d78602bbe1690498a77ee",
    "path": "data/outputs/provider_human_acceptance_receipt_verification.json"
  },
  {
    "checksum_sha256": "17bd99391c54fcb732f1be6e4350b1cd2f30ec15b7dc32677e01299ca665211d",
    "path": "data/outputs/provider_shadow_run_comparison.json"
  }
]
```

## Recommended provider allowlist PR

- Title: Allowlist the_odds_api staging provider
- Description:

Adds `the_odds_api` (`odds_api`) to the reviewed staging provider allowlist for 1x2, total_2_5. Binds the policy entry to human acceptance receipt `odds_api-20260817T155217-0400-8204291a2b19` and its verified evidence. Known limitations: BTTS is not requested by the current provider adapter. Missing BTTS prices remain unavailable and must never be fabricated. Allowlisting does not bypass staging validation, freshness, completeness, checksum, receipt, or Thursday cutoff gates. This policy-only proposal does not promote staging, run a provider, generate picks, place bets, or enable cron.

## Decision boundary

A ready bundle proves which evidence bytes were reviewed; it does not make the policy change. Provider allowlisting remains a separate PR, and cron remains disabled until a later independent review explicitly enables it.