/**
 * Google Apps Script for live Google Sheet auto-updates.
 * Supports both main tracker and "Pending Review" tabs!
 * 
 * Instructions:
 * 1. Open your Google Sheet: https://docs.google.com/spreadsheets/d/1Naq2pmSfyt8ulXpq-7SKFmXfaerYnvkbjSy83SXRmT0/edit?usp=sharing
 * 2. In the top menu, click: Extensions > Apps Script
 * 3. Replace all code with this entire script and click Save (disk icon).
 * 4. Click "Deploy" (top right) > "Manage deployments" (or "New deployment")
 *    - Edit the deployment > change version to "New version"
 *    - Click "Deploy".
 */

function doPost(e) {
  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var payload = JSON.parse(e.postData.contents);
    var targetSheetName = payload.sheet || "Job Tracker";
    
    var sheet = ss.getSheetByName(targetSheetName);
    
    // Auto-create "Pending Review" tab if it does not exist yet
    if (!sheet) {
      if (targetSheetName === "Pending Review") {
        sheet = ss.insertSheet("Pending Review");
        var headers = ["Company", "Role", "Location", "Experience", "Tech", "Job URL", "Review Reason", "Confidence"];
        sheet.appendRow(headers);
        sheet.getRange(1, 1, 1, headers.length).setFontWeight("bold").setBackground("#FFF2CC");
      } else {
        sheet = ss.getActiveSheet();
      }
    }
    
    var rows = payload.rows || [];
    for (var i = 0; i < rows.length; i++) {
      sheet.appendRow(rows[i]);
    }
    
    return ContentService.createTextOutput(JSON.stringify({
      status: "success",
      sheet: targetSheetName,
      added: rows.length
    })).setMimeType(ContentService.MimeType.JSON);
    
  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({
      status: "error",
      message: err.toString()
    })).setMimeType(ContentService.MimeType.JSON);
  }
}
