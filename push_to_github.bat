@echo off
title Push to GitHub
echo ========================================================
echo   Pushing Job Agent to GitHub: dhananjaykr9/job_agent
echo ========================================================
echo.

git remote remove origin 2>nul
git remote add origin https://github.com/dhananjaykr9/job_agent.git
git branch -M main
git add .
git commit -m "Initialize AI Job Discovery Agent with hourly GitHub Actions workflow"
git push -u origin main

echo.
echo ========================================================
echo   Push complete!
echo ========================================================
pause
