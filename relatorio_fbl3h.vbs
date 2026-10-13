' Extrai a FBL3H (partidas em aberto) da conta do fundo fixo e salva em TXT.
' Argumentos (passados pelo fundo_fixo.py): pasta, empresa, conta, nome do arquivo.
Dim pasta, empresa, conta, arquivo
pasta = "Z:\15. MELHORIAS\FUNDO FIXO\temp"
empresa = "BR21"
conta = "28200202"
arquivo = "fundo_fixo.txt"
If WScript.Arguments.Count >= 1 Then pasta = WScript.Arguments(0)
If WScript.Arguments.Count >= 2 Then empresa = WScript.Arguments(1)
If WScript.Arguments.Count >= 3 Then conta = WScript.Arguments(2)
If WScript.Arguments.Count >= 4 Then arquivo = WScript.Arguments(3)

If Not IsObject(application) Then
   Set SapGuiAuto  = GetObject("SAPGUI")
   Set application = SapGuiAuto.GetScriptingEngine
End If
If Not IsObject(connection) Then
   Set connection = application.Children(0)
End If
If Not IsObject(session) Then
   Set session    = connection.Children(0)
End If
If IsObject(WScript) Then
   WScript.ConnectObject session,     "on"
   WScript.ConnectObject application, "on"
End If
session.findById("wnd[0]").maximize
session.findById("wnd[0]/tbar[0]/okcd").text = "/nFBL3H"
session.findById("wnd[0]").sendVKey 0
session.findById("wnd[0]/usr/ctxtS_CCODE-LOW").text = empresa
session.findById("wnd[0]/usr/ctxtS_RACCT-LOW").text = conta
session.findById("wnd[0]/usr/ctxtP_LAYOUT").text = "/AGING"
session.findById("wnd[0]/usr/chkP_OUTFI").selected = true
session.findById("wnd[0]/usr/ctxtP_DFILE").setFocus
session.findById("wnd[0]").sendVKey 4
session.findById("wnd[1]/usr/ctxtDY_PATH").text = pasta
session.findById("wnd[1]/usr/ctxtDY_FILENAME").text = arquivo
session.findById("wnd[1]/tbar[0]/btn[11]").press
session.findById("wnd[0]/tbar[1]/btn[8]").press
session.findById("wnd[1]/tbar[0]/btn[0]").press
session.findById("wnd[0]/tbar[0]/btn[12]").press
session.findById("wnd[0]/tbar[0]/btn[12]").press
