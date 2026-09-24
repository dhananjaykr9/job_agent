/**
 * Google Apps Script for live Google Sheet auto-updates.
 * 
 * Instructions:
 * 1. Open your Google Sheet: https://docs.google.com/spreadsheets/d/1Naq2pmSfyt8ulXpq-7SKFmXfaerYnvkbjSy83SXRmT0/edit?usp=sharing
 * 2. In the top menu, click: Extensions > Apps Script
 * 3. Delete any default code and paste this entire code.
 * 4. Click "Deploy" (top right) > "New deployment"
 * 5. Select type: "Web app" (click the gear icon if needed)
 *    - Description: "Job Discovery Webhook"
 *    - Execute as: "Me"
 *    - Who has access: "Anyone"
 * 6. Click "Deploy", authorize access with your Google account.
 * 7. Copy the "Web app URL" (it looks like: https://script.google.com/macros/s/AKfycb.../exec)
 * 8. Add it as GOOGLE_SHEET_WEBHOOK_URL in your GitHub Secrets and .env!
 */

function doPost(e) {
  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sheet = ss.getActiveSheet();
    var payload = JSON.parse(e.postData.contents);
    var rows = payload.rows || [];
    
    for (var i = 0; i < rows.length; i++) {
      sheet.appendRow(rows[i]);
    }
    
    return ContentService.createTextOutput(JSON.stringify({
      status: "success",
      added: rows.length
    })).setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({
      status: "error",
      message: err.toString()
    })).setMimeType(ContentService.MimeType.JSON);
  }
}
