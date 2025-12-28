Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")

' Obtém o caminho da pasta onde este arquivo VBS está
CurrentDirectory = FSO.GetParentFolderName(WScript.ScriptFullName)

' Caminho completo para o arquivo .bat
BatPath = CurrentDirectory & "\iniciar_bot.bat"

' O número 0 no final é o código para rodar invisível (Hide)
WshShell.Run chr(34) & BatPath & chr(34), 0

Set WshShell = Nothing
Set FSO = Nothing