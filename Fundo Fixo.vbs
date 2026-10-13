Option Explicit
Dim fso, sh, pasta
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
pasta = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = pasta
On Error Resume Next
sh.Run "pyw """ & pasta & "\fundo_fixo.py"" app", 0, False
If Err.Number <> 0 Then
  MsgBox "Não consegui iniciar o Python (pyw). Confira se o Python está instalado." & vbCrLf & Err.Description, vbExclamation, "Fundo Fixo"
End If
