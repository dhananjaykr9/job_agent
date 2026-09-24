' AI Job Discovery Agent - Background Launcher
' Runs the agent silently in the background without any CMD window
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = scriptDir
WshShell.Run "pythonw.exe cli.py schedule", 0, False
