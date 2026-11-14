' Antigravity 无感自愈启动器
' 后台静默检测并修复钩子，然后调起官方应用（无黑框弹窗）

Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

themeRoot = "E:\lyh\theme"
appExe = WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\antigravity\Antigravity.exe"

' 优先寻找系统绝对路径 Python，若不存在则回退至 PATH
pythonExe = "python"
If fso.FileExists("C:\Python314\python.exe") Then
    pythonExe = "C:\Python314\python.exe"
ElseIf fso.FileExists(WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python312\python.exe") Then
    pythonExe = WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python312\python.exe"
End If

' 1. 静默体检：如果钩子被官方更新冲掉了，后台自动静默修复
verifyCmd = """" & pythonExe & """ """ & themeRoot & "\scripts\patch_asar.py"" verify"
ret = WshShell.Run(verifyCmd, 0, True)

If ret <> 0 Then
    ' 钩子缺失，执行静默安装
    installCmd = """" & pythonExe & """ """ & themeRoot & "\scripts\patch_asar.py"" install"
    WshShell.Run installCmd, 0, True
End If

' 2. 调起 Antigravity 官方客户端
If fso.FileExists(appExe) Then
    WshShell.Run """" & appExe & """", 1, False
Else
    MsgBox "未找到 Antigravity 客户端：" & vbCrLf & appExe, vbCritical, "启动失败"
End If
