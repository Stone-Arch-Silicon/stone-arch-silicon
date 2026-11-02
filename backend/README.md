# SASi website backend

The site itself is static files on GitHub Pages. Everything that stores or
sends anything runs on Google, under the club account SASI@umn.edu:

- Join and sponsor forms: this folder. A Google Apps Script web app adds each
  submission as a row in a Google Sheet it creates, and emails the board.
- Events: the SASI@umn.edu Google Calendar, read by `assets/calendar.js`
  with a restricted API key.

Nothing runs on anyone's own computer or server, and no secret lives in this
repository.

## Set it up (about 10 minutes, once)

Do all of this signed in as SASI@umn.edu, so the club owns it and it survives
officer turnover.

1. Go to script.google.com and click New project. Name it "SASi website backend".
2. Replace the contents of `Code.gs` with `backend/Code.gs` from this repo.
3. In Project Settings, tick "Show appsscript.json manifest file in editor", then replace `appsscript.json` with `backend/appsscript.json`. That also turns on the Google Sheets API service the script uses.
4. Back in the editor, pick `setup` in the function menu and click Run. Approve the permissions it asks for: "See, edit, create, and delete only the specific Google Drive files you use with this app" and "Send email as you". It creates the "SASi website" sheet, with Join and Sponsors tabs, and prints its link in the log.
5. Pick `testJoin` and click Run. A test row appears in the Join tab and SASI@umn.edu gets an email. Delete the test row.
6. Click Deploy, then New deployment. Type: Web app. Execute as: Me. Who has access: Anyone. Click Deploy and copy the Web app URL (it ends in `/exec`).
7. Paste that URL into `BACKEND_URL` at the top of `assets/backend.js` and commit. The forms on join.html and sponsor.html switch on by themselves. Until then those pages show the Google Form and email links instead.

The script is a standalone project rather than one opened from the Sheet's
Extensions menu, because that menu fails when a browser is signed in to more
than one Google account. It finds its Sheet through the SHEET_ID script
property that `setup` saves.

To change the backend later, edit the code, then Deploy, Manage deployments,
edit the existing deployment, and pick New version. That keeps the same URL.

## Who can see the data

- The Sheet is private to SASI@umn.edu. Share it with board members by name,
  never with "Anyone with the link".
- "Who has access: Anyone" only means anyone can submit a form. The script
  only ever appends rows. It never sends Sheet data back, so a visitor can't
  read what anyone else submitted.
- The script runs as SASI@umn.edu with two narrow permissions: the Drive
  files it created itself (just the "SASi website" sheet), and sending mail.
  It can't open any other file in the account.

## Spam and abuse

- A hidden "website" field catches bots that fill in every input.
- Forms submitted faster than 1.5 seconds after the page loads are refused.
- One submission per email address per form every 10 minutes.
- At most 60 submissions an hour across all forms, which keeps Google's daily
  email quota safe.
- Every field is length-limited and checked against its allowed options, and
  links are refused in name fields.
- Every value is written as raw text, so a submission that starts with `=`
  can't run as a spreadsheet formula.

## Calendar API key

`assets/calendar.js` holds a Google API key. That key is public by design,
since every visitor's browser uses it, so its protection is the restrictions
on it in Google Cloud Console (APIs and Services, then Credentials):

- Application restrictions: Websites, listing only the site's addresses, for
  example `https://stone-arch-silicon.github.io/*`. Add the custom domain here
  the day it goes live, or the calendar stops loading on it.
- API restrictions: Google Calendar API only.

The calendar itself must stay public with "See all event details", since the
site can only show public events.
