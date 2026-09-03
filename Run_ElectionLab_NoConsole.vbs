Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
appDir = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = fso.BuildPath(appDir, ".venv\Scripts\pythonw.exe")
target = fso.BuildPath(appDir, "ElectionLab.pyw")

If fso.FileExists(pythonw) Then
  shell.CurrentDirectory = appDir
  shell.Run """" & pythonw & """ """ & target & """", 0, False
Else
  MsgBox "ElectionLab environment is not installed yet. Run Install_ElectionLab.bat first.", 48, "ElectionLab"
End If
