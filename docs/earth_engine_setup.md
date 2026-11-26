# Earth Engine setup

You do every sign-in yourself. Nothing in this guide asks you to share a password, and the project ID never goes into the repo.

Checked against Google's documentation on 2026-11-25:
[Earth Engine access](https://developers.google.com/earth-engine/guides/access),
[noncommercial tiers](https://developers.google.com/earth-engine/guides/noncommercial_tiers),
[authentication](https://developers.google.com/earth-engine/guides/auth).

## 1. Pick the Google account

Use the account whose Google Drive will receive the exports. It needs about 10 GB free in Drive for one batch at a time.

## 2. Create a Cloud project

1. Open https://console.cloud.google.com/projectcreate
2. Give it a name such as `my-ee-project`. Google shows a **project ID** under the name. Write it down. You will put it in an environment variable in step 5.

## 3. Register the project for noncommercial Earth Engine use

1. Open https://console.cloud.google.com/earth-engine and choose your new project. This registration page also turns on the Earth Engine API for you.
2. Choose noncommercial (unpaid) use and fill out the questionnaire. **Answer it truthfully.** Google verifies every noncommercial project and decides eligibility. If Google judges the use commercial, noncommercial access is not available. Describe the project as it is: independent research aimed at a peer-reviewed publication, with code and results published openly.
3. **Choose a quota tier.** Since April 27, 2026, noncommercial projects get a monthly compute quota in EECU-hours, and batch exports count against it.
   - **Community:** 150 EECU-hours per month. No billing account needed.
   - **Contributor:** 1,000 EECU-hours per month. Needs an active billing account for identity verification, but Earth Engine noncommercial use is not charged. Other Google Cloud services used in the same project are billed normally.
   - Going over the quota does not stop tasks. The project runs slower in a restricted mode until the quota resets on the first of the month (Pacific Time).
   - **My suggestion:** start with Community. The pilot export in Phase 3 measures real use. If the projection does not fit, you can switch to Contributor on the Manage Tier page (https://console.cloud.google.com/earth-engine/configuration/manage-tier) without starting over.
4. Note that noncommercial status must be reverified every year.

## 4. Sign in from this computer

Type this at the Claude Code prompt. The leading `!` runs it in this session so we can both see the result:

```
! conda run --no-capture-output -n rs-trends earthengine authenticate --auth_mode=localhost
```

A browser window opens. Sign in with the account from step 1 and grant access. The token is saved to `C:\Users\<you>\.config\earthengine\credentials`, which is outside the repo. Never copy that file into the repo.

If the browser does not open, run the same command without `--auth_mode=localhost` and follow the link it prints.

## 5. Set the environment variables

Open your own PowerShell window (not through Claude Code, so the project ID stays out of the chat transcript) and run:

```powershell
setx EE_PROJECT "<your-project-id>"
setx RS_DATA_DIR "C:\rsdata"
```

`setx` saves the values for future sessions. **Close and reopen Claude Code** afterwards, because programs that were already open do not see new values.

## 6. Check everything

```
! conda run -n rs-trends python src/00_check_setup.py
```

You should see `ALL CHECKS PASSED`. It confirms the packages, the config, the data folder, that Earth Engine starts with your project, and that all four Landsat collections are readable. The project ID is shown masked, for example `tex*********`.

## Troubleshooting

| Message | Fix |
|---|---|
| `EE_PROJECT is not set` | Step 5, then restart Claude Code |
| `could not initialize Earth Engine` with a permission or "not registered" error | Finish step 3 for that exact project ID |
| `could not initialize` with a credentials error | Repeat step 4 |
| `conda: command not found` in Git Bash | Run `conda init bash` in the Anaconda Prompt, then restart |
