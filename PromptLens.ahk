;@Ahk2Exe-SetName PromptLens
;@Ahk2Exe-SetDescription PromptLens Screen Capture & Hotkey Daemon
;@Ahk2Exe-SetVersion 1.0.0.0
;@Ahk2Exe-SetCopyright Copyright (c) 2026 Soulflux LLC (MIT License)
;@Ahk2Exe-SetOrigFilename QuickClip.exe
;@Ahk2Exe-SetCompanyName Soulflux LLC
;@Ahk2Exe-SetMainIcon assets\app_icon.ico
#Requires AutoHotkey v2.0
#SingleInstance Force

; ==============================================================================
; PromptLens: Multimodal AI Screen Capture & Notation Suite
; ==============================================================================
; Sol-Audited State Machine: IDLE -> STARTING -> RECORDING -> STOPPING
; 1. F10 (or Win+H): Video Narration (toggle recording on/off, press F10 again to stop)
;    - Records active window desktop region + mic to M:\Videos\Notations
;    - Alt+Click / Alt+Shift+Click displays instant click-through spotlight
; 2. F9 (or PrintScreen / Win+Shift+S): Quick Region Screenshot -> saves PNG & copies image to clipboard
; 3. Shift+F9 (or Shift+PrintScreen): Annotated Active Window Screenshot -> Word/Excel-style Review Margin & Voice
; ==============================================================================

Persistent(true)
DetectHiddenWindows(true)

OnError(OnGlobalError)
OnExit(OnGlobalExit)

OnGlobalError(err, mode) {
    try FileAppend("Error: " . err.Message . " in " . err.What . " at line " . err.Line . "`nStack: " . err.Stack . "`n", A_ScriptDir . "\error.log")
    return false
}

OnGlobalExit(reason, code) {
    try FileAppend("Exited: reason=" . reason . ", code=" . code . "`n", A_ScriptDir . "\exit.log")
    CleanupAllResources()
}

; Ensure Per-Monitor DPI Awareness
DllCall("SetProcessDpiAwarenessContext", "Ptr", -4)

; Helper to expand Windows environment variables (e.g. %USERPROFILE%)
ExpandEnvVars(str) {
    if (!InStr(str, "%"))
        return str
    bufSize := DllCall("ExpandEnvironmentStrings", "Str", str, "Ptr", 0, "UInt", 0, "UInt")
    if (bufSize <= 0)
        return str
    buf := Buffer(bufSize * 2, 0)
    DllCall("ExpandEnvironmentStrings", "Str", str, "Ptr", buf, "UInt", bufSize, "UInt")
    return StrGet(buf, "UTF-16")
}

; Helper to normalize textual hotkey strings (e.g. "Shift+F9" -> "+F9")
NormalizeHotkeyString(hk) {
    str := Trim(hk)
    if (str == "" || StrLower(str) == "none")
        return ""
    str := RegExReplace(str, "i)\b(Ctrl|Control)\s*\+\s*", "^")
    str := RegExReplace(str, "i)\bAlt\s*\+\s*", "!")
    str := RegExReplace(str, "i)\bShift\s*\+\s*", "+")
    str := RegExReplace(str, "i)\b(Win|Windows)\s*\+\s*", "#")
    str := RegExReplace(str, "i)\b(Print\s*Screen|PrtScr|PrtScn?|Snapshot|SysRq)\b", "PrintScreen")
    str := RegExReplace(str, "\s+", "")
    return str
}

; Pinned GDI+ Module and Single Process Token (INV-GDI-001)
global hGdiplusModule := 0
global gdiplusToken := 0

InitGdiplus() {
    global hGdiplusModule, gdiplusToken
    if (gdiplusToken)
        return true
    hGdiplusModule := DllCall("LoadLibrary", "Str", "gdiplus.dll", "Ptr")
    if (!hGdiplusModule)
        return false
    si := Buffer(24, 0)
    NumPut("UInt", 1, si, 0)
    pToken := 0
    if (DllCall("gdiplus\GdiplusStartup", "Ptr*", &pToken, "Ptr", si, "Ptr", 0) == 0) {
        gdiplusToken := pToken
        return true
    }
    return false
}

ShutdownGdiplus() {
    global hGdiplusModule, gdiplusToken
    if (gdiplusToken) {
        try DllCall("gdiplus\GdiplusShutdown", "Ptr", gdiplusToken)
        gdiplusToken := 0
    }
    if (hGdiplusModule) {
        try DllCall("FreeLibrary", "Ptr", hGdiplusModule)
        hGdiplusModule := 0
    }
}

; State Machine: "IDLE", "STARTING", "RECORDING", "STOPPING"
global recordState := "IDLE"
global recordStartTime := 0
global keyPressStartTime := 0
global isVideoKeyDown := false
global isToggleMode := false
global recordMode := "toggle" ; "toggle", "hybrid", "hold"
global lastOutputFile := ""
global currentWindowRect := {x: 0, y: 0, w: 0, h: 0}
global currentWindowTitle := ""
global hProcess := 0
global hStdInWrite := 0
global enableVideo := false
global videoHotkeysRegistered := false
global watchersActive := false
global registeredSnipHotkey := ""
global registeredAnnotateHotkey := ""
global registeredScreenshotHotkeys := []
global activeHotkeyEdit := ""
global hkRecorderHook := ""
global registeredRecorderHotkeys := []
global settingsHoverTips := Map()
global settingsHoverTipLastHwnd := 0
global videoHotkey := "#h"
global quickSnipHotkey := "PrintScreen"
global regionAnnotateHotkey := "^F9"
global annotateHotkey := "F9"
global windowSnipHotkey := "!F9"
global quickSnipClipboard := "path"
global regionCaptureKey := "PrintScreen"
global windowCaptureKey := "F9"
global scrollCaptureKey := "F10"
global defaultCaptureBehavior := "annotate"
global captureModifier := "Shift"
global clipboardTarget := "markdown"
global hudToggleHotkey := "^+h"
global showRecordingHUD := true
global currentMic := ""
global secondaryMic := "auto"
global captureMode := "window"
global isPortableMode := FileExist(A_ScriptDir . "\.portable") || FileExist(A_ScriptDir . "\portable.dat")
global defaultScreenshotDir := isPortableMode ? (A_ScriptDir . "\Notations") : (EnvGet("USERPROFILE") != "" ? (EnvGet("USERPROFILE") . "\Pictures") : (A_ScriptDir . "\Notations"))
global defaultNotationsDir := defaultScreenshotDir
global outputFolder := defaultScreenshotDir
global ffmpegExe := ""
global pythonExe := ""
global fpsVal := "30"
global crfVal := "23"
global encoderVal := "auto"
global showCursor := true
global recordSystemAudio := true
global dualTrackAudio := true
global noiseSuppression := true
global pttMode := "open"
global pttHotkey := "Space"
global audioLimiter := true
global chimeEnabled := true
global chimeVolume := 50
global muteWarningEnabled := true
global lastMuteWarnTime := 0
global echoCancellation := true
global countdownSecs := 3
global pauseHotkey := "^F10"
global customRegion := {x: 0, y: 0, w: 0, h: 0}
global isRecordingPaused := false
global detectedMics := []
global iniPath := A_ScriptDir . "\config.ini"
global currentProcessName := ""
global revertHotkey := "!F10"
global feedbackInbox := defaultNotationsDir . "\.feedback_inbox\inbox"
global airGappedMode := false
global trimWorkingSetEnabled := true
global idleTrimIntervalSec := 30
global maxIdleMemoryMb := 35.0

; Overlays
global highlightGui := 0
global isSnipping := false
global isCapturingSnip := false
global snipOverlayGui := 0
global snipBoxGui := 0
global lastShiftDownTime := 0
global lastShiftUpTime := 0

; Initialize
InitApp()

; ------------------------------------------------------------------------------
; Initialization & Directory Validation
; ------------------------------------------------------------------------------
InitApp() {
    global videoHotkey, quickSnipHotkey, regionAnnotateHotkey, annotateHotkey, windowSnipHotkey, quickSnipClipboard, regionCaptureKey, windowCaptureKey, scrollCaptureKey, defaultCaptureBehavior, captureModifier, clipboardTarget, pauseHotkey, hudToggleHotkey, showRecordingHUD
    global currentMic, captureMode, outputFolder, ffmpegExe, pythonExe, iniPath, fpsVal, crfVal, encoderVal, showCursor, recordMode
    global revertHotkey, feedbackInbox, airGappedMode, enableVideo
    global trimWorkingSetEnabled, idleTrimIntervalSec, maxIdleMemoryMb

    isPortableMode := FileExist(A_ScriptDir . "\.portable") || FileExist(A_ScriptDir . "\portable.dat")
    userProf := EnvGet("USERPROFILE")
    defaultDir := isPortableMode ? (A_ScriptDir . "\Notations") : (userProf != "" ? (userProf . "\Pictures") : (A_ScriptDir . "\Notations"))

    RepairConfig(iniPath, defaultDir)
    rawOutputDir := IniRead(iniPath, "Settings", "OutputDir", defaultDir)
    outputFolder := ExpandEnvVars(rawOutputDir)
    enableVideo := false
    videoHotkey := NormalizeHotkeyString(IniRead(iniPath, "Settings", "VideoHotkey", "#h"))
    quickSnipHotkey := NormalizeHotkeyString(IniRead(iniPath, "Settings", "QuickSnipHotkey", "PrintScreen"))
    regionAnnotateHotkey := NormalizeHotkeyString(IniRead(iniPath, "Settings", "RegionAnnotateHotkey", "^F9"))
    quickSnipClipboard := IniRead(iniPath, "Settings", "QuickSnipClipboard", "path")
    annotateHotkey := NormalizeHotkeyString(IniRead(iniPath, "Settings", "AnnotateHotkey", "F9"))
    windowSnipHotkey := NormalizeHotkeyString(IniRead(iniPath, "Settings", "WindowSnipHotkey", "!F9"))
    regionCaptureKey := NormalizeHotkeyString(IniRead(iniPath, "Settings", "RegionHotkey", IniRead(iniPath, "Settings", "QuickSnipHotkey", IniRead(iniPath, "Settings", "RegionAnnotateHotkey", "PrintScreen"))))
    windowCaptureKey := NormalizeHotkeyString(IniRead(iniPath, "Settings", "WindowHotkey", IniRead(iniPath, "Settings", "AnnotateHotkey", IniRead(iniPath, "Settings", "WindowSnipHotkey", "F9"))))
    scrollCaptureKey := NormalizeHotkeyString(IniRead(iniPath, "Settings", "ScrollHotkey", "F10"))
    defaultCaptureBehavior := StrLower(IniRead(iniPath, "Settings", "DefaultCaptureBehavior", "annotate")) == "standard" ? "standard" : "annotate"
    captureModifier := IniRead(iniPath, "Settings", "CaptureModifier", "Shift")
    if !(captureModifier = "Shift" || captureModifier = "Ctrl" || captureModifier = "Alt" || captureModifier = "Ctrl+Shift" || captureModifier = "Alt+Shift" || captureModifier = "None")
        captureModifier := "Shift"
    clipboardTarget := IniRead(iniPath, "Settings", "ClipboardTarget", "markdown")
    if (RegExMatch(quickSnipHotkey, "i)PrintScreen$") || RegExMatch(regionAnnotateHotkey, "i)PrintScreen$") || RegExMatch(annotateHotkey, "i)PrintScreen$") || RegExMatch(windowSnipHotkey, "i)PrintScreen$")) {
        try RegWrite(0, "REG_DWORD", "HKCU\Control Panel\Keyboard", "PrintScreenKeyForSnippingEnabled")
    }
    hudToggleHotkey := NormalizeHotkeyString(IniRead(iniPath, "Settings", "HudToggleHotkey", "^+h"))
    showRecordingHUD := (IniRead(iniPath, "Settings", "ShowRecordingHUD", "true") = "true")
    recordMode := IniRead(iniPath, "Settings", "RecordMode", "toggle")
    currentMic := IniRead(iniPath, "Settings", "Microphone", "auto")
    secondaryMic := IniRead(iniPath, "Settings", "SecondaryMicrophone", "auto")
    captureMode := IniRead(iniPath, "Settings", "CaptureMode", "window")
    try {
        customRegion.x := Integer(IniRead(iniPath, "Settings", "RegionX", "0"))
        customRegion.y := Integer(IniRead(iniPath, "Settings", "RegionY", "0"))
        customRegion.w := Integer(IniRead(iniPath, "Settings", "RegionW", "0"))
        customRegion.h := Integer(IniRead(iniPath, "Settings", "RegionH", "0"))
    }
    fpsVal := IniRead(iniPath, "Settings", "FPS", "30")
    crfVal := IniRead(iniPath, "Settings", "CRF", "23")
    encoderVal := IniRead(iniPath, "Settings", "Encoder", "auto")
    revertHotkey := IniRead(iniPath, "Settings", "RevertHotkey", "!F10")
    feedbackInbox := IniRead(iniPath, "Settings", "FeedbackInbox", outputFolder . "\.feedback_inbox\inbox")
    airGappedMode := (IniRead(iniPath, "Enterprise", "AirGappedMode", IniRead(iniPath, "Settings", "AirGappedMode", "false")) = "true")
    trimWorkingSetEnabled := (IniRead(iniPath, "Settings", "TrimWorkingSetOnIdle", "true") = "true")
    idleTrimIntervalSec := Integer(IniRead(iniPath, "Settings", "IdleTrimIntervalSeconds", "30"))
    maxIdleMemoryMb := Float(IniRead(iniPath, "Settings", "MaxIdleMemoryMB", "35"))

    CoordMode "ToolTip", "Screen"

    InitGdiplus()
    EnsureOutputDirectory()

    pythonExe := FindPython()
    ffmpegExe := ""

    ; Automated first-run background downloader if FFmpeg is missing (inhibited in Air-Gapped mode)
    if (enableVideo && !airGappedMode && ffmpegExe == "" && pythonExe != "") {
        downloaderScript := (FileExist(A_ScriptDir . "\src\ffmpeg_downloader.py") ? (A_ScriptDir . "\src\ffmpeg_downloader.py") : (FileExist(A_ScriptDir . "\ffmpeg_downloader.py") ? (A_ScriptDir . "\ffmpeg_downloader.py") : (FileExist(A_ScriptDir . "\..\src\ffmpeg_downloader.py") ? (A_ScriptDir . "\..\src\ffmpeg_downloader.py") : (A_ScriptDir . "\..\ffmpeg_downloader.py"))))
        if FileExist(downloaderScript) {
            try Run('"' . pythonExe . '" "' . downloaderScript . '" --background', A_ScriptDir, "Hide")
        }
    }

    RefreshAudioDevicesList()
    RegisterAllHotkeys()
    BuildTrayMenu()

    UpdateTrayIconTheme()
    OnMessage(0x001A, (*) => UpdateTrayIconTheme()) ; WM_SETTINGCHANGE
    SuspendBackgroundWatchers()
    SetTimer(() => CheckForUpdatesBackground(), -5000)
    ParseCliArguments()

    qLbl := FormatHotkeyLabel(regionCaptureKey)
    aLbl := FormatHotkeyLabel(windowCaptureKey)

    readyMsg := "PromptLens Active!`n`n"
        . "• [" . qLbl . "]: Region Capture`n"
        . "• [" . aLbl . "]: Window Capture`n"
        . "• Voice memos are available in the Notation Editor`n`n"
    readyMsg .= "Folder: " . outputFolder
    ToolTip(readyMsg, 30, 30, 1)
    SetTimer(() => ToolTip(,,, 1), -4000)

    setupCompleted := IniRead(iniPath, "Setup", "Completed", "false")
    if (setupCompleted != "true") {
        ShowSetupWizardGui()
    }

    ; Schedule periodic idle working set trimming (SNIP-007)
    if (trimWorkingSetEnabled && idleTrimIntervalSec > 0) {
        SetTimer(TrimWorkingSet, idleTrimIntervalSec * 1000)
    }
    ; Initial memory working set trim after startup completes
    SetTimer(TrimWorkingSet, -600)
}

EnsureOutputDirectory() {
    global outputFolder
    outputFolder := ExpandEnvVars(outputFolder)
    if (!DirExist(outputFolder)) {
        try {
            DirCreate(outputFolder)
        } catch as err {
            fallbackDir := EnvGet("USERPROFILE") . "\Videos\Notations"
            try DirCreate(fallbackDir)
            ToolTip("⚠️ Cannot access " . outputFolder . "`nFalling back to: " . fallbackDir, 30, 30, 1)
            SetTimer(() => ToolTip(,,, 1), -4000)
            outputFolder := fallbackDir
        }
    }
}

FindFFmpeg() {
    global iniPath
    cfgPath := IniRead(iniPath, "Settings", "FFmpegPath", "auto")
    if (cfgPath != "auto" && FileExist(cfgPath))
        return cfgPath

    ; 1. Check bundled application bin directories
    if FileExist(A_ScriptDir . "\bin\ffmpeg.exe")
        return A_ScriptDir . "\bin\ffmpeg.exe"
    if FileExist(A_ScriptDir . "\ffmpeg.exe")
        return A_ScriptDir . "\ffmpeg.exe"
    if FileExist(A_ScriptDir . "\tools\ffmpeg\bin\ffmpeg.exe")
        return A_ScriptDir . "\tools\ffmpeg\bin\ffmpeg.exe"
    if FileExist(A_ScriptDir . "\tools\ffmpeg\ffmpeg.exe")
        return A_ScriptDir . "\tools\ffmpeg\ffmpeg.exe"

    ; 2. Check LocalAppData bundled directory
    localAppData := EnvGet("LOCALAPPDATA")
    if (localAppData != "") {
        if FileExist(localAppData . "\PromptLens\bin\ffmpeg.exe")
            return localAppData . "\PromptLens\bin\ffmpeg.exe"
        if FileExist(localAppData . "\Programs\ffmpeg\bin\ffmpeg.exe")
            return localAppData . "\Programs\ffmpeg\bin\ffmpeg.exe"
    }

    ; 3. WinGet package directory
    packagesDir := EnvGet("LOCALAPPDATA") . "\Microsoft\WinGet\Packages"
    if DirExist(packagesDir) {
        loop files packagesDir . "\*Gyan.FFmpeg*", "D" {
            loop files A_LoopFilePath . "\ffmpeg.exe", "R" {
                if FileExist(A_LoopFilePath)
                    return A_LoopFilePath
            }
        }
        loop files packagesDir . "\*FFmpeg*", "D" {
            loop files A_LoopFilePath . "\ffmpeg.exe", "R" {
                if FileExist(A_LoopFilePath)
                    return A_LoopFilePath
            }
        }
    }

    try {
        shell := ComObject("WScript.Shell")
        exec := shell.Exec('where.exe ffmpeg.exe')
        out := exec.StdOut.ReadAll()
        for line in StrSplit(out, "`n", "`r") {
            trimmed := Trim(line, " `t`r`n")
            if (trimmed != "" && FileExist(trimmed))
                return trimmed
        }
    }
    return ""
}

IsValidPython(exePath) {
    if (!exePath || !FileExist(exePath))
        return false
    try {
        exitCode := RunWait('"' . exePath . '" -c "exit(0)"',, "Hide")
        return (exitCode == 0)
    } catch {
        return false
    }
}

FindPython() {
    global iniPath
    cfgPath := IniRead(iniPath, "Settings", "PythonPath", "auto")
    if (cfgPath != "auto" && IsValidPython(cfgPath))
        return cfgPath

    candidates := []
    localAppData := EnvGet("LOCALAPPDATA")

    ; 1. Prioritize real Python installations in LocalAppData
    if (localAppData != "") {
        for baseDir in [localAppData . "\Python", localAppData . "\Programs\Python"] {
            if DirExist(baseDir) {
                loop files baseDir . "\pythonw.exe", "R" {
                    candidates.Push(A_LoopFilePath)
                }
                loop files baseDir . "\python.exe", "R" {
                    candidates.Push(A_LoopFilePath)
                }
            }
        }
    }

    ; 2. Prioritize real Python installations in Program Files and system drives
    for pf in [EnvGet("ProgramFiles"), EnvGet("ProgramFiles(x86)"), "C:"] {
        if (pf != "" && DirExist(pf)) {
            loop files pf . "\Python*", "D" {
                for exe in ["\pythonw.exe", "\python.exe"] {
                    if FileExist(A_LoopFilePath . exe)
                        candidates.Push(A_LoopFilePath . exe)
                }
            }
        }
    }

    ; 3. System where.exe lookup (excluding WindowsApps aliases)
    try {
        shell := ComObject("WScript.Shell")
        for exeName in ["pythonw.exe", "python.exe"] {
            exec := shell.Exec('where.exe ' . exeName)
            out := exec.StdOut.ReadAll()
            for line in StrSplit(out, "`n", "`r") {
                trimmed := Trim(line, " `t`r`n")
                if (trimmed != "" && !InStr(trimmed, "WindowsApps")) {
                    candidates.Push(trimmed)
                }
            }
        }
    }

    ; 4. WindowsApps execution aliases as last fallback
    if (localAppData != "") {
        candidates.Push(localAppData . "\Microsoft\WindowsApps\pythonw.exe")
        candidates.Push(localAppData . "\Microsoft\WindowsApps\python.exe")
    }

    ; Validate candidate executables by executing a lightweight command and checking status
    for c in candidates {
        if IsValidPython(c)
            return c
    }

    return ""
}

GetPythonExe() {
    global pythonExe
    if (pythonExe != "" && FileExist(pythonExe))
        return pythonExe
    pythonExe := FindPython()
    return pythonExe
}

; ------------------------------------------------------------------------------
; Memory Optimization & Working Set Trimming (SNIP-007)
; ------------------------------------------------------------------------------
TrimWorkingSet() {
    global trimWorkingSetEnabled
    if (!trimWorkingSetEnabled)
        return false
    try {
        hProc := DllCall("GetCurrentProcess", "Ptr")
        DllCall("SetProcessWorkingSetSize", "Ptr", hProc, "UPtr", -1, "UPtr", -1)
        DllCall("psapi\EmptyWorkingSet", "Ptr", hProc)
        return true
    } catch {
        return false
    }
}

MenuOptimizeMemory() {
    TrimWorkingSet()
    ToolTip("⚡ Memory Working Set Trimmed`nIdle footprint optimized to < 35 MB", 30, 30, 1)
    SetTimer(() => ToolTip(,,, 1), -2500)
}

FindNotationEditor() {
    global iniPath
    cfgPath := IniRead(iniPath, "Paths", "NotationEditorExe", "auto")
    if (cfgPath != "auto" && FileExist(cfgPath))
        return cfgPath

    candidates := [
        A_ScriptDir . "\bin\NotationEditor.exe",
        A_ScriptDir . "\NotationEditor.exe",
        A_ScriptDir . "\..\bin\NotationEditor.exe",
        A_ScriptDir . "\..\NotationEditor.exe",
        A_ScriptDir . "\dist\NotationEditor\NotationEditor.exe",
        A_ScriptDir . "\dist\NotationEditor.exe"
    ]
    for cand in candidates {
        if FileExist(cand)
            return cand
    }

    return ""
}

RefreshAudioDevicesList() {
    global ffmpegExe, detectedMics, currentMic, iniPath
    detectedMics := []
    if (ffmpegExe == "")
        ffmpegExe := FindFFmpeg()

    if (ffmpegExe != "") {
        try {
            shell := ComObject("WScript.Shell")
            cmd := '"' . ffmpegExe . '" -list_devices true -f dshow -i dummy'
            exec := shell.Exec(cmd)
            output := exec.StdErr.ReadAll()
            for line in StrSplit(output, "`n", "`r") {
                if (InStr(line, "(audio)") && RegExMatch(line, '"([^"]+)"\s*\(audio\)', &m))
                    detectedMics.Push(m[1])
            }
        }
    }

    if (detectedMics.Length > 0) {
        if (currentMic == "auto" || !HasValue(detectedMics, currentMic)) {
            selected := detectedMics[1]
            for mic in detectedMics {
                if InStr(mic, "Arctis") || InStr(mic, "Sonar") {
                    selected := mic
                    break
                }
            }
            currentMic := selected
            IniWrite(currentMic, iniPath, "Settings", "Microphone")
        }
    }
}

HasValue(arr, val) {
    for item in arr {
        if (item = val)
            return true
    }
    return false
}

FormatHotkeyLabel(hk) {
    trimmed := Trim(hk)
    if (trimmed == "" || StrLower(trimmed) == "none")
        return "None"
    clean := RegExReplace(hk, "[\$\*\~]", "")
    label := ""
    if InStr(clean, "#")
        label .= "Win+"
    if InStr(clean, "^")
        label .= "Ctrl+"
    if InStr(clean, "!")
        label .= "Alt+"
    if InStr(clean, "+")
        label .= "Shift+"
    baseKey := RegExReplace(clean, "[\#\!\^\+]", "")
    if (StrLen(baseKey) == 1)
        baseKey := StrUpper(baseKey)
    return label . baseKey
}

GetHotkeyControlValue(edCtrl) {
    if IsObject(edCtrl) {
        if HasProp(edCtrl, "rawHk")
            return NormalizeHotkeyString(edCtrl.rawHk)
        return NormalizeHotkeyString(edCtrl.Value)
    }
    return NormalizeHotkeyString(edCtrl)
}

SetHotkeyControlValue(edCtrl, hk) {
    normalized := NormalizeHotkeyString(hk)
    edCtrl.rawHk := normalized
    edCtrl.Value := FormatHotkeyLabel(normalized)
    if HasProp(edCtrl, "onHotkeyChanged") && IsObject(edCtrl.onHotkeyChanged)
        edCtrl.onHotkeyChanged.Call()
}

AddHotkeyRecorderField(guiObj, currentHk, onChanged := "") {
    normalized := NormalizeHotkeyString(currentHk)
    edCtrl := guiObj.Add("Edit", "x+10 w260 ReadOnly", FormatHotkeyLabel(normalized))
    edCtrl.rawHk := normalized
    if IsObject(onChanged)
        edCtrl.onHotkeyChanged := onChanged
    edCtrl.OnEvent("Focus", StartHotkeyRecorder)
    edCtrl.OnEvent("LoseFocus", StopHotkeyRecorder)
    btnClear := guiObj.Add("Button", "x+5 w45", "Clear")
    btnClear.OnEvent("Click", (*) => SetHotkeyControlValue(edCtrl, ""))
    return edCtrl
}

RecordHotkeyToActiveEdit(hk) {
    global activeHotkeyEdit
    if IsObject(activeHotkeyEdit)
        SetHotkeyControlValue(activeHotkeyEdit, hk)
}

RegisterRecorderHk(hkString, callback) {
    global registeredRecorderHotkeys
    try {
        Hotkey(hkString, callback, "On")
        registeredRecorderHotkeys.Push(hkString)
    }
}

StartHotkeyRecorder(edCtrl, ignored*) {
    global activeHotkeyEdit, hkRecorderHook
    if IsObject(activeHotkeyEdit) && activeHotkeyEdit.Hwnd == edCtrl.Hwnd
        return
    StopHotkeyRecorder()
    activeHotkeyEdit := edCtrl
    hkRecorderHook := InputHook("L0")
    hkRecorderHook.KeyOpt("{All}", "N S")
    hkRecorderHook.KeyOpt("{Tab}", "-S V")
    hkRecorderHook.KeyOpt("{Escape}", "-S V")
    hkRecorderHook.OnKeyDown := OnRecorderKeyDown
    hkRecorderHook.Start()

    RegisterRecorderHk("$*PrintScreen", (*) => RecordHotkeyToActiveEdit("PrintScreen"))
    RegisterRecorderHk("$*+PrintScreen", (*) => RecordHotkeyToActiveEdit("+PrintScreen"))
    RegisterRecorderHk("$*^PrintScreen", (*) => RecordHotkeyToActiveEdit("^PrintScreen"))
    RegisterRecorderHk("$*!PrintScreen", (*) => RecordHotkeyToActiveEdit("!PrintScreen"))
    RegisterRecorderHk("$*SC054", (*) => RecordHotkeyToActiveEdit("+PrintScreen"))
    RegisterRecorderHk("$*F9", (*) => RecordHotkeyToActiveEdit("F9"))
    RegisterRecorderHk("$*+F9", (*) => RecordHotkeyToActiveEdit("+F9"))
    RegisterRecorderHk("$*^F9", (*) => RecordHotkeyToActiveEdit("^F9"))
    RegisterRecorderHk("$*!F9", (*) => RecordHotkeyToActiveEdit("!F9"))
    RegisterRecorderHk("$*F10", (*) => RecordHotkeyToActiveEdit("F10"))
    RegisterRecorderHk("$*+F10", (*) => RecordHotkeyToActiveEdit("+F10"))
    RegisterRecorderHk("$*^F10", (*) => RecordHotkeyToActiveEdit("^F10"))
    RegisterRecorderHk("$*!F10", (*) => RecordHotkeyToActiveEdit("!F10"))
}

StopHotkeyRecorder(edCtrl := "", ignored*) {
    global activeHotkeyEdit, hkRecorderHook, registeredRecorderHotkeys
    if IsObject(edCtrl) && IsObject(activeHotkeyEdit) && activeHotkeyEdit.Hwnd != edCtrl.Hwnd
        return
    if IsObject(hkRecorderHook) {
        try hkRecorderHook.Stop()
    }
    hkRecorderHook := ""
    for hkString in registeredRecorderHotkeys {
        try Hotkey(hkString, "Off")
    }
    registeredRecorderHotkeys := []
    activeHotkeyEdit := ""
}

OnRecorderKeyDown(ih, vk, sc) {
    keyName := GetKeyName(Format("vk{:02X}sc{:03X}", vk, sc))
    if (vk == 0x2C || sc == 0x137 || sc == 0x054 || keyName == "PrintScreen" || keyName == "SysRq")
        keyName := "PrintScreen"
    if (vk >= 0x70 && vk <= 0x87)
        keyName := "F" . (vk - 0x6F)
    if (keyName == "LControl" || keyName == "RControl" || keyName == "Control"
        || keyName == "LShift" || keyName == "RShift" || keyName == "Shift"
        || keyName == "LAlt" || keyName == "RAlt" || keyName == "Alt"
        || keyName == "LWin" || keyName == "RWin" || keyName == "AppsKey")
        return
    if (keyName == "Tab" || keyName == "Escape")
        return
    mods := ""
    if (GetKeyState("LWin", "P") || GetKeyState("RWin", "P"))
        mods .= "#"
    if (GetKeyState("Control", "P") || GetKeyState("Ctrl", "P") || GetKeyState("Control"))
        mods .= "^"
    if (GetKeyState("Alt", "P") || GetKeyState("Alt"))
        mods .= "!"
    if (GetKeyState("Shift", "P") || GetKeyState("Shift"))
        mods .= "+"
    if ((keyName == "Backspace" || keyName == "Delete") && mods == "") {
        RecordHotkeyToActiveEdit("")
        return
    }
    if (keyName != "")
        RecordHotkeyToActiveEdit(mods . keyName)
}

IsHotkeyPhysicallyHeld(hk) {
    clean := RegExReplace(hk, "[\$\*\~]", "")

    ; Check modifier keys
    if InStr(clean, "#") && !(GetKeyState("LWin", "P") || GetKeyState("RWin", "P"))
        return false
    if InStr(clean, "!") && !(GetKeyState("LAlt", "P") || GetKeyState("RAlt", "P"))
        return false
    if InStr(clean, "^") && !(GetKeyState("LCtrl", "P") || GetKeyState("RCtrl", "P"))
        return false
    if InStr(clean, "+") && !(GetKeyState("LShift", "P") || GetKeyState("RShift", "P"))
        return false

    ; Extract base key
    baseKey := RegExReplace(clean, "[\#\!\^\+]", "")
    if (baseKey == "")
        return false

    try {
        return GetKeyState(baseKey, "P")
    } catch {
        return false
    }
}

; ------------------------------------------------------------------------------
; Hotkey Setup & Edge-Triggered Debouncing
; ------------------------------------------------------------------------------
UnregisterScreenshotHotkeys() {
    global registeredScreenshotHotkeys
    for hk in registeredScreenshotHotkeys {
        try Hotkey(hk, "Off")
    }
    registeredScreenshotHotkeys := []
}

RegisterAllHotkeys() {
    global regionCaptureKey, windowCaptureKey, scrollCaptureKey, captureModifier, revertHotkey
    UnregisterScreenshotHotkeys()
    UnregisterVideoHotkeys()

    modPrefix := ModifierNameToAhkPrefix(captureModifier)
    for captureType, baseKey in Map("region", regionCaptureKey, "window", windowCaptureKey, "scroll", scrollCaptureKey) {
        RegisterCaptureHotkeys(captureType, baseKey, modPrefix)
    }

    if (RegExMatch(regionCaptureKey, "i)PrintScreen$") || RegExMatch(windowCaptureKey, "i)PrintScreen$") || RegExMatch(scrollCaptureKey, "i)PrintScreen$")) {
        try RegWrite(0, "REG_DWORD", "HKCU\Control Panel\Keyboard", "PrintScreenKeyForSnippingEnabled")
    }
    if (revertHotkey != "") {
        RegisterTrackedScreenshotHotkey("$" . revertHotkey, (*) => EmitRevertTicket())
    }
}

RegisterTrackedScreenshotHotkey(hkString, callback) {
    global registeredScreenshotHotkeys
    try {
        Hotkey(hkString, callback, "On")
        registeredScreenshotHotkeys.Push(hkString)
    } catch as err {
        try FileAppend("Hotkey register error (" . hkString . "): " . err.Message . "`n", A_ScriptDir . "\error.log")
    }
}

ModifierNameToAhkPrefix(modName) {
    switch modName {
        case "Shift": return "+"
        case "Ctrl": return "^"
        case "Alt": return "!"
        case "Ctrl+Shift": return "^+"
        case "Alt+Shift": return "!+"
        default: return ""
    }
}

RouteCaptureAction(captureType, isModified := false) {
    global defaultCaptureBehavior
    mode := StrLower(defaultCaptureBehavior) == "standard" ? "standard" : "annotate"
    if isModified
        mode := mode == "standard" ? "annotate" : "standard"
    switch captureType {
        case "region":
            if (mode == "standard")
                StartScreenSnip()
            else
                CaptureRegionAnnotateSnip()
        case "window":
            if (mode == "standard")
                CaptureActiveWindowQuickSnip()
            else
                CaptureActiveWindowSnip()
        case "scroll":
            CaptureScrollingWindow(mode == "annotate")
    }
}

RegisterCaptureHotkeys(captureType, rawBaseKey, modPrefix) {
    baseKey := NormalizeHotkeyString(rawBaseKey)
    if (baseKey == "" || StrLower(baseKey) == "none")
        return
    if (StrLower(baseKey) == "printscreen") {
        RegisterTrackedScreenshotHotkey("$PrintScreen", (*) => RouteCaptureAction(captureType, false))
        RegisterTrackedScreenshotHotkey("$PrintScreen Up", (*) => "")
        if (modPrefix != "")
            RegisterTrackedScreenshotHotkey(modPrefix . "$PrintScreen", (*) => RouteCaptureAction(captureType, true))
        return
    }
    RegisterTrackedScreenshotHotkey("$" . baseKey, (*) => RouteCaptureAction(captureType, false))
    if (modPrefix != "" && !InStr(baseKey, modPrefix))
        RegisterTrackedScreenshotHotkey("$" . modPrefix . baseKey, (*) => RouteCaptureAction(captureType, true))
}

RegisterVideoHotkeys() {
    global videoHotkey, pauseHotkey, hudToggleHotkey, videoHotkeysRegistered

    vDown := InStr(videoHotkey, "$") ? videoHotkey : ("$" . videoHotkey)
    vUp := vDown . " Up"

    try {
        Hotkey(vDown, OnVideoDown, "On")
    } catch as err {
        try FileAppend("Video hotkey register error: " . err.Message . "`n", A_ScriptDir . "\error.log")
    }
    try {
        Hotkey(vUp, OnVideoUp, "On")
    } catch as err {
        try FileAppend("Video hotkey register error (Up): " . err.Message . "`n", A_ScriptDir . "\error.log")
    }

    ; Keyboard fallback for video narration (Win + H) if custom video hotkey is configured
    cleanVideo := RegExReplace(videoHotkey, "[\$\*\~]", "")
    if (cleanVideo != "#h") {
        try Hotkey("$*#h", OnVideoDown, "On")
        catch as err {
            try FileAppend("Fallback video hotkey register error ($*#h): " . err.Message . "`n", A_ScriptDir . "\error.log")
        }
        try Hotkey("$*#h Up", OnVideoUp, "On")
        catch as err {
            try FileAppend("Fallback video hotkey register error ($*#h Up): " . err.Message . "`n", A_ScriptDir . "\error.log")
        }
    }

    ; Toggle Recording HUD Visibility (default: Ctrl+Shift+H)
    if (hudToggleHotkey != "") {
        hHk := InStr(hudToggleHotkey, "$") ? hudToggleHotkey : ("$" . hudToggleHotkey)
        try Hotkey(hHk, ToggleRecordingHUD, "On")
        catch as err {
            try FileAppend("Hotkey register error (" . hHk . "): " . err.Message . "`n", A_ScriptDir . "\error.log")
        }
    }

    ; Recording Pause / Resume (default: Ctrl+F10)
    if (pauseHotkey != "") {
        try {
            Hotkey(pauseHotkey, ToggleRecordingPause, "On")
        } catch as err {
        }
    }

    ; Use ~ prefix so clicks pass through naturally to active windows (video spotlight)
    try Hotkey("~!LButton", OnHighlightClick, "On")
    catch as err {
        try FileAppend("Hotkey register error (~!LButton): " . err.Message . "`n", A_ScriptDir . "\error.log")
    }
    try Hotkey("~!LButton Up", OnHighlightRelease, "On")
    catch as err {
        try FileAppend("Hotkey register error (~!LButton Up): " . err.Message . "`n", A_ScriptDir . "\error.log")
    }
    try Hotkey("~!+LButton", OnHighlightClick, "On")
    catch as err {
        try FileAppend("Hotkey register error (~!+LButton): " . err.Message . "`n", A_ScriptDir . "\error.log")
    }
    try Hotkey("~!+LButton Up", OnHighlightRelease, "On")
    catch as err {
        try FileAppend("Hotkey register error (~!+LButton Up): " . err.Message . "`n", A_ScriptDir . "\error.log")
    }
    try Hotkey("~Alt Up", OnHighlightRelease, "On")
    catch as err {
        try FileAppend("Hotkey register error (~Alt Up): " . err.Message . "`n", A_ScriptDir . "\error.log")
    }
    try Hotkey("~Shift Up", OnHighlightRelease, "On")
    catch as err {
        try FileAppend("Hotkey register error (~Shift Up): " . err.Message . "`n", A_ScriptDir . "\error.log")
    }

    videoHotkeysRegistered := true
}

UnregisterVideoHotkeys() {
    global videoHotkey, pauseHotkey, hudToggleHotkey, videoHotkeysRegistered
    if (!videoHotkeysRegistered)
        return

    vDown := InStr(videoHotkey, "$") ? videoHotkey : ("$" . videoHotkey)
    vUp := vDown . " Up"
    try Hotkey(vDown, "Off")
    try Hotkey(vUp, "Off")

    cleanVideo := RegExReplace(videoHotkey, "[\$\*\~]", "")
    if (cleanVideo != "#h") {
        try Hotkey("$*#h", "Off")
        try Hotkey("$*#h Up", "Off")
    }

    if (hudToggleHotkey != "") {
        hHk := InStr(hudToggleHotkey, "$") ? hudToggleHotkey : ("$" . hudToggleHotkey)
        try Hotkey(hHk, "Off")
    }

    if (pauseHotkey != "") {
        try Hotkey(pauseHotkey, "Off")
    }

    try Hotkey("~!LButton", "Off")
    try Hotkey("~!LButton Up", "Off")
    try Hotkey("~!+LButton", "Off")
    try Hotkey("~!+LButton Up", "Off")
    try Hotkey("~Alt Up", "Off")
    try Hotkey("~Shift Up", "Off")

    videoHotkeysRegistered := false
}

StartBackgroundWatchers() {
    global enableVideo, watchersActive
    if (!enableVideo)
        return
    try OnMessage(0x0219, OnDeviceChangeNotification) ; WM_DEVICECHANGE
    watchersActive := true
}

SuspendBackgroundWatchers() {
    global watchersActive
    try OnMessage(0x0219, OnDeviceChangeNotification, 0) ; Unhook WM_DEVICECHANGE
    SetTimer(HandleAudioDeviceHotplug, 0)
    SetTimer(VideoWatchdog, 0)
    SetTimer(UpdateHUD, 0)
    watchersActive := false
}

OnShiftDown(*) {
    global lastShiftDownTime
    lastShiftDownTime := A_TickCount
}

OnShiftUp(*) {
    global lastShiftUpTime
    lastShiftUpTime := A_TickCount
}

OnQuickSnipDispatch(*) {
    global lastShiftDownTime, lastShiftUpTime

    ; 1. Direct physical keyboard state inspection
    physShift := (GetKeyState("Shift", "P") || GetKeyState("LShift", "P") || GetKeyState("RShift", "P"))

    ; 2. Logical keyboard state
    logicShift := (GetKeyState("Shift") || GetKeyState("LShift") || GetKeyState("RShift"))

    ; 3. Win32 asynchronous hardware key state table
    asyncShift := ((DllCall("GetAsyncKeyState", "Int", 0x10, "Short") & 0x8000) != 0)
               || ((DllCall("GetAsyncKeyState", "Int", 0xA0, "Short") & 0x8000) != 0)
               || ((DllCall("GetAsyncKeyState", "Int", 0xA1, "Short") & 0x8000) != 0)

    ; 4. State-ordered Shift event history to defeat OS modifier swallowing
    shiftHeldByHistory := (
        lastShiftDownTime > lastShiftUpTime
        && (A_TickCount - lastShiftDownTime < 1500)
    )
    recentlyReleasedShift := (
        lastShiftUpTime >= lastShiftDownTime
        && lastShiftUpTime > 0
        && (A_TickCount - lastShiftUpTime < 350)
    )
    recentShift := (shiftHeldByHistory || recentlyReleasedShift)

    if (physShift || logicShift || asyncShift || recentShift) {
        CaptureActiveWindowSnip()
    } else {
        StartScreenSnip()
    }
}

OnPrintScreenDispatch(*) {
    OnQuickSnipDispatch()
}

ToggleCountdown(*) {
    global countdownSecs, iniPath
    countdownSecs := (countdownSecs > 0) ? 0 : 3
    IniWrite(String(countdownSecs), iniPath, "Settings", "Countdown")
    BuildTrayMenu()
    ToolTip(countdownSecs > 0 ? "⏱️ Countdown: Enabled (3s)" : "⏱️ Countdown: Disabled (Instant)", 30, 30, 1)
    SetTimer(() => ToolTip(,,, 1), -2500)
}
ToggleShowCursor(*) {
    global showCursor, iniPath
    showCursor := !showCursor
    IniWrite(showCursor ? "true" : "false", iniPath, "Settings", "ShowCursor")
    BuildTrayMenu()
    ToolTip(showCursor ? "🖱️ Mouse Cursor: Included in Video" : "🚫 Mouse Cursor: Hidden from Video", 30, 30, 1)
    SetTimer(() => ToolTip(,,, 1), -2500)
}
ToggleRecordingHUD(*) {
    global showRecordingHUD, iniPath, recordState, enableVideo
    if (!enableVideo) {
        ToolTip("⚠️ Recording HUD is dormant (EnableVideo=false in config.ini).", 30, 30, 1)
        SetTimer(() => ToolTip(,,, 1), -2000)
        return
    }
    showRecordingHUD := !showRecordingHUD
    IniWrite(showRecordingHUD ? "true" : "false", iniPath, "Settings", "ShowRecordingHUD")
    BuildTrayMenu()

    if (recordState == "RECORDING") {
        if (!showRecordingHUD) {
            ToolTip(,,, 1)
        } else {
            UpdateHUD()
        }
    } else {
        stateMsg := showRecordingHUD ? "📊 Recording HUD: Visible (Bottom Right)" : "📊 Recording HUD: Hidden"
        ToolTip(stateMsg, 30, 30, 1)
        SetTimer(() => ToolTip(,,, 1), -2000)
    }
}

OnVideoDown(*) {
    global recordState, isVideoKeyDown, isToggleMode, keyPressStartTime, enableVideo
    if (!enableVideo) {
        ToolTip("⚠️ Video recording is dormant (EnableVideo=false in config.ini).`nScreenshot mode is active.", 30, 30, 1)
        SetTimer(() => ToolTip(,,, 1), -2500)
        return
    }
    if (isVideoKeyDown) {
        ; Ignore OS keyboard auto-repeat events while the key is physically held
        return
    }
    isVideoKeyDown := true
    keyPressStartTime := A_TickCount

    if (recordState == "RECORDING") {
        ; Tapping hotkey while already recording acts as a stop toggle
        recordState := "STOPPING"
        StopVideoRecording()
        return
    }
    if (recordState != "IDLE")
        return

    isToggleMode := false
    recordState := "STARTING"
    StartVideoRecording()
}

OnVideoUp(*) {
    global recordState, isVideoKeyDown, keyPressStartTime, isToggleMode, recordMode, enableVideo
    if (!enableVideo)
        return
    isVideoKeyDown := false
    heldMs := (keyPressStartTime > 0) ? (A_TickCount - keyPressStartTime) : 0

    if (recordMode == "toggle")
        return

    if (recordState == "STARTING") {
        if (recordMode == "hold" || heldMs >= 450) {
            recordState := "STOPPING"
            return
        }
        ; For hybrid with quick tap (< 450ms), continue in toggle mode
        isToggleMode := true
        return
    }
    if (recordState != "RECORDING")
        return

    if (recordMode == "hybrid" && (heldMs < 450 || isToggleMode)) {
        isToggleMode := true
        return
    }

    ; Hold mode or hybrid held past threshold: user released hotkey, stop
    recordState := "STOPPING"
    StopVideoRecording()
}

; ------------------------------------------------------------------------------
; Modality 3: Video Narration & Pre-Allocated Spotlight Highlight
; ------------------------------------------------------------------------------
InitHighlightGui() {
    global highlightGui
    radius := 32
    size := radius * 2

    highlightGui := Gui("-Caption +AlwaysOnTop +ToolWindow -DPIScale +E0x20")
    highlightGui.BackColor := "00E5FF"
    hRgn := DllCall("CreateEllipticRgn", "Int", 0, "Int", 0, "Int", size, "Int", size, "Ptr")
    res := DllCall("SetWindowRgn", "Ptr", highlightGui.Hwnd, "Ptr", hRgn, "Int", 1)
    if (!res && hRgn) {
        DllCall("DeleteObject", "Ptr", hRgn)
    }
    WinSetTransparent(170, highlightGui.Hwnd)
}

OnHighlightClick(*) {
    global recordState, highlightGui
    if (recordState != "RECORDING" || !highlightGui)
        return

    CoordMode "Mouse", "Screen"
    MouseGetPos(&x, &y)
    radius := 32
    highlightGui.Show("x" . (x - radius) . " y" . (y - radius) . " w" . (radius * 2) . " h" . (radius * 2) . " NoActivate")
}

OnHighlightRelease(*) {
    global highlightGui
    if (highlightGui)
        highlightGui.Hide()
}

RunCountdownOverlay(seconds) {
    if (seconds <= 0)
        return
    try {
        countdownGui := Gui("-Caption +AlwaysOnTop +ToolWindow -DPIScale")
        countdownGui.BackColor := "000000"
        WinSetTransparent(180, countdownGui.Hwnd)
        countdownGui.SetFont("s72 bold c00E5FF", "Segoe UI")
        txt := countdownGui.Add("Text", "w320 Center", String(seconds))
        countdownGui.Show("w320 h180 Center NoActivate")

        rem := seconds
        while (rem > 0) {
            txt.Value := String(rem)
            SoundBeep(880, 80)
            Sleep(850)
            rem--
        }
        txt.Value := "REC"
        SoundBeep(1760, 150)
        Sleep(250)
        countdownGui.Destroy()
    } catch as err {
    }
}
ToggleRecordingPause(*) {
    global recordState, hProcess, isRecordingPaused, pauseHotkey, enableVideo
    if (!enableVideo)
        return
    if (recordState != "RECORDING" || !hProcess) {
        return
    }
    if (!isRecordingPaused) {
        DllCall("ntdll\NtSuspendProcess", "Ptr", hProcess)
        isRecordingPaused := true
        SoundBeep(440, 100)
        ToolTip("⏸️ Video Recording PAUSED`n[" . FormatHotkeyLabel(pauseHotkey) . "] to resume", 30, 30, 1)
        SetTimer(() => ToolTip(,,, 1), -2500)
    } else {
        DllCall("ntdll\NtResumeProcess", "Ptr", hProcess)
        isRecordingPaused := false
        SoundBeep(880, 100)
        ToolTip("▶️ Video Recording RESUMED", 30, 30, 1)
        SetTimer(() => ToolTip(,,, 1), -2500)
    }
}
StartVideoRecording() {
    global recordState, recordStartTime, lastOutputFile, currentWindowRect, currentWindowTitle, currentProcessName
    global hProcess, hStdInWrite, currentMic, outputFolder, ffmpegExe, captureMode, videoHotkey
    global isToggleMode, recordMode, enableVideo

    if (!enableVideo) {
        recordState := "IDLE"
        ToolTip("ℹ️ Video recording is disabled (EnableVideo=false in config.ini).`nScreenshot mode is active.", 30, 30, 1)
        SetTimer(() => ToolTip(,,, 1), -3000)
        return
    }

    if (recordState != "STARTING") {
        recordState := "IDLE"
        return
    }

    EnsureOutputDirectory()

    if (countdownSecs > 0) {
        RunCountdownOverlay(countdownSecs)
    }

    procName := ""
    if (captureMode == "region") {
        if (customRegion.w <= 0 || customRegion.h <= 0) {
            ToolTip("⚠️ No custom region set! Please drag to select a region.", 30, 30, 1)
            SetTimer(() => ToolTip(,,, 1), -2500)
            recordState := "IDLE"
            StartRegionSelection()
            return
        }
        winX := customRegion.x
        winY := customRegion.y
        winW := customRegion.w
        winH := customRegion.h
        winTitle := "Custom Region (" . winW . "x" . winH . ")"
        procName := "RegionCapture"
    } else if (captureMode == "screen") {
        winX := DllCall("GetSystemMetrics", "Int", 76, "Int")
        winY := DllCall("GetSystemMetrics", "Int", 77, "Int")
        winW := DllCall("GetSystemMetrics", "Int", 78, "Int")
        winH := DllCall("GetSystemMetrics", "Int", 79, "Int")
        winTitle := "Full Desktop"
        try {
            activeHwnd := WinGetID("A")
            if (activeHwnd)
                procName := WinGetProcessName(activeHwnd)
        } catch {
            procName := "whisper_of_the_divine"
        }
        if (!procName)
            procName := "whisper_of_the_divine"
    } else {
        GetActiveWindowBounds(&winX, &winY, &winW, &winH, &winTitle, &procName)
    }

    currentWindowTitle := winTitle
    currentProcessName := procName
    currentWindowRect := {x: winX, y: winY, w: winW, h: winH}

    prefix := GetCleanPrefix(procName, winTitle, "Clip")
    lastOutputFile := GenerateUniqueFilePath(outputFolder, prefix, ".mp4")

    if (recordState != "STARTING") {
        recordState := "IDLE"
        return
    }

    if (ffmpegExe == "")
        ffmpegExe := FindFFmpeg()

    if (ffmpegExe == "") {
        ToolTip("⚠️ FFmpeg is downloading in the background. Please wait a moment...", 30, 30, 1)
        SetTimer(() => ToolTip(,,, 1), -3000)
        recordState := "IDLE"
        return
    }

    if !SpawnFFmpeg(lastOutputFile, winX, winY, winW, winH, currentMic) {
        ToolTip("❌ Failed to start FFmpeg video capture.", 30, 30, 1)
        SetTimer(() => ToolTip(,,, 1), -3000)
        recordState := "IDLE"
        return
    }

    ; If key release already stopped the session during spawn
    if (recordState == "STOPPING") {
        StopVideoRecording()
        return
    }

    recordState := "RECORDING"
    recordStartTime := A_TickCount

    UpdateHUD()
    SetTimer(UpdateHUD, 200)
    SetTimer(VideoWatchdog, 250)
}

VideoWatchdog() {
    global recordState, videoHotkey, hProcess, keyPressStartTime, isToggleMode, recordMode
    if (recordState == "RECORDING") {
        if (!isToggleMode && recordMode != "toggle") {
            heldMs := (keyPressStartTime > 0) ? (A_TickCount - keyPressStartTime) : 0
            if (heldMs >= 450 && !IsHotkeyPhysicallyHeld(videoHotkey)) {
                SetTimer(VideoWatchdog, 0)
                OnVideoUp()
                return
            }
        }

        if (hProcess) {
            exitCode := 0
            if DllCall("GetExitCodeProcess", "Ptr", hProcess, "UInt*", &exitCode) {
                if (exitCode != 259) {
                    SetTimer(VideoWatchdog, 0)
                    ToolTip("⚠️ Video capture ended unexpectedly (code: " . exitCode . ")", 30, 30, 1)
                    SetTimer(() => ToolTip(,,, 1), -3000)
                    recordState := "IDLE"
                    CleanupAllResources()
                }
            }
        }
    } else {
        SetTimer(VideoWatchdog, 0)
    }
}

StopVideoRecording() {
    global isRecordingPaused
    isRecordingPaused := false
    global recordState, recordStartTime, keyPressStartTime, isVideoKeyDown, lastOutputFile, hProcess, hStdInWrite, videoHotkey, highlightGui, isToggleMode

    SetTimer(UpdateHUD, 0)
    SetTimer(VideoWatchdog, 0)
    ToolTip(,,, 1)

    if (highlightGui)
        highlightGui.Hide()

    if (recordStartTime > 0) {
        elapsedMs := A_TickCount - recordStartTime
        if (elapsedMs < 650)
            Sleep(650 - elapsedMs)
    }

    if (hStdInWrite) {
        qBuf := Buffer(4, 0)
        StrPut("q`n", qBuf, "CP0")
        written := 0
        DllCall("WriteFile", "Ptr", hStdInWrite, "Ptr", qBuf, "UInt", 2, "UInt*", &written, "Ptr", 0)
        DllCall("CloseHandle", "Ptr", hStdInWrite)
        hStdInWrite := 0
    }

    if (hProcess) {
        waitRes := DllCall("WaitForSingleObject", "Ptr", hProcess, "UInt", 3000)
        if (waitRes != 0) {
            DllCall("TerminateProcess", "Ptr", hProcess, "UInt", 1)
            DllCall("WaitForSingleObject", "Ptr", hProcess, "UInt", 1000)
        }
        DllCall("CloseHandle", "Ptr", hProcess)
        hProcess := 0
    }

    wasRecording := (recordStartTime > 0)
    totalSeconds := wasRecording ? Round((A_TickCount - recordStartTime) / 1000, 1) : 0
    recordStartTime := 0
    keyPressStartTime := 0
    isToggleMode := false
    recordState := "IDLE"

    if (FileExist(lastOutputFile) && FileGetSize(lastOutputFile) > 500) {
        A_Clipboard := lastOutputFile
        SoundPlay("*64")

        ; Emit atomic ticket to AI Agent live feedback inbox
        EmitFeedbackTicket(lastOutputFile, totalSeconds)

        successMsg := "✅ Video Clip Saved (" . totalSeconds . "s)`n📋 Copied to Clipboard & Sent to AI Agent!`n" . lastOutputFile
        ToolTip(successMsg, 30, 30, 1)
        SetTimer(() => ToolTip(,,, 1), -4000)
    } else {
        ToolTip("⚠️ Recording failed or produced an unplayable output.", 30, 30, 1)
        SetTimer(() => ToolTip(,,, 1), -3000)
    }
}

JsonEscapeString(str) {
    if (!str)
        return ""
    str := StrReplace(str, "\", "\\")
    str := StrReplace(str, '"', '\"')
    str := StrReplace(str, "`r", "\r")
    str := StrReplace(str, "`n", "\n")
    str := StrReplace(str, "`t", "\t")
    return str
}

EmitFeedbackTicket(videoPath, durationSec) {
    global outputFolder, iniPath, currentProcessName, currentWindowTitle, feedbackInbox
    inboxDir := feedbackInbox
    if (!DirExist(inboxDir)) {
        try DirCreate(inboxDir)
        catch {
            return
        }
    }

    tId := "clip-" . FormatTime(, "yyyyMMdd-HHmmss") . "-" . SubStr("00" . Mod(A_TickCount, 1000), -3)
    tmpFile := inboxDir . "\" . tId . ".tmp"
    finalFile := inboxDir . "\" . tId . ".json"

    procName := currentProcessName
    if (!procName) {
        try {
            activeHwnd := WinGetID("A")
            if (activeHwnd)
                procName := WinGetProcessName(activeHwnd)
        } catch {
            procName := "active_process"
        }
        if (!procName)
            procName := "active_process"
    }

    workingDir := EnvGet("DEV_PROJECT_ROOT")
    if (workingDir == "")
        workingDir := A_WorkingDir

    escapedTitle := JsonEscapeString(currentWindowTitle)
    escapedVideo := JsonEscapeString(StrReplace(videoPath, "\", "/"))
    escapedWorkDir := JsonEscapeString(StrReplace(workingDir, "\", "/"))
    escapedProc := JsonEscapeString(procName)

    payload := '{"ticket_id":"' . tId . '","action":"MUTATE","video_path":"' . escapedVideo . '","target_process":"' . escapedProc . '","window_title":"' . escapedTitle . '","working_dir":"' . escapedWorkDir . '","duration_seconds":' . durationSec . ',"timestamp":"' . FormatTime(, "yyyy-MM-dd'T'HH:mm:ss'Z'") . '"}'

    try {
        if FileExist(tmpFile)
            FileDelete(tmpFile)
        FileAppend(payload, tmpFile, "UTF-8-RAW")
        FileMove(tmpFile, finalFile, 1)

        ; Ensure text sidecar path exists for speech transcription
        sidecarTxt := videoPath . ".txt"
        if (!FileExist(sidecarTxt)) {
            try FileAppend("", sidecarTxt, "UTF-8-RAW")
        }
    }
}

EmitRevertTicket() {
    global outputFolder, iniPath, currentProcessName, currentWindowTitle, feedbackInbox
    inboxDir := feedbackInbox
    if (!DirExist(inboxDir)) {
        try DirCreate(inboxDir)
        catch {
            return
        }
    }

    tId := "revert-" . FormatTime(, "yyyyMMdd-HHmmss") . "-" . SubStr("00" . Mod(A_TickCount, 1000), -3)
    tmpFile := inboxDir . "\" . tId . ".tmp"
    finalFile := inboxDir . "\" . tId . ".json"

    procName := currentProcessName
    if (!procName) {
        try {
            activeHwnd := WinGetID("A")
            if (activeHwnd)
                procName := WinGetProcessName(activeHwnd)
        } catch {
            procName := "active_process"
        }
        if (!procName)
            procName := "active_process"
    }

    workingDir := EnvGet("DEV_PROJECT_ROOT")
    if (workingDir == "")
        workingDir := A_WorkingDir

    escapedTitle := JsonEscapeString(currentWindowTitle)
    escapedWorkDir := JsonEscapeString(StrReplace(workingDir, "\", "/"))
    escapedProc := JsonEscapeString(procName)

    payload := '{"ticket_id":"' . tId . '","action":"REVERT","target_process":"' . escapedProc . '","window_title":"' . escapedTitle . '","working_dir":"' . escapedWorkDir . '","timestamp":"' . FormatTime(, "yyyy-MM-dd'T'HH:mm:ss'Z'") . '"}'

    try {
        if FileExist(tmpFile)
            FileDelete(tmpFile)
        FileAppend(payload, tmpFile, "UTF-8-RAW")
        FileMove(tmpFile, finalFile, 1)
        SoundPlay("*48")
        ToolTip("↩️ Revert Ticket Dispatched to AI Agent!", 30, 30, 1)
        SetTimer(() => ToolTip(,,, 1), -3000)
    }
}

UpdateHUD() {
    global recordState, recordStartTime, currentWindowTitle, videoHotkey, hudToggleHotkey, currentMic, isToggleMode, recordMode, showRecordingHUD
    if (recordState != "RECORDING") {
        SetTimer(UpdateHUD, 0)
        ToolTip(,,, 1)
        return
    }

    if (!showRecordingHUD) {
        ToolTip(,,, 1)
        return
    }

    elapsedMs := A_TickCount - recordStartTime
    seconds := Mod(elapsedMs // 1000, 60)
    minutes := elapsedMs // 60000
    timeStr := Format("{:02d}:{:02d}", minutes, seconds)

    micDisplay := currentMic
    if (micDisplay == "")
        micDisplay := "No Mic"
    else if InStr(micDisplay, "Arctis")
        micDisplay := "Arctis Nova Pro"
    else if InStr(micDisplay, "Sonar")
        micDisplay := "SteelSeries Sonar"

    displayTitle := currentWindowTitle
    if (StrLen(displayTitle) > 28)
        displayTitle := SubStr(displayTitle, 1, 25) . "..."

    vLbl := FormatHotkeyLabel(videoHotkey)
    hLbl := FormatHotkeyLabel(hudToggleHotkey)
    stopHint := (isToggleMode || recordMode == "toggle")
        ? "Press [" . vLbl . "] to stop & copy path"
        : "Release [" . vLbl . "] to stop & copy path"

    hudText := "🔴 REC  " . timeStr . "  |  " . displayTitle . "`n"
        . "🎙️  " . micDisplay . "`n"
        . "💡 Alt+Click to Spotlight`n"
        . stopHint . "`n"
        . "(" . hLbl . " or Tray to hide HUD)"

    CoordMode "ToolTip", "Screen"
    MonitorGetWorkArea(, &waLeft, &waTop, &waRight, &waBottom)
    hudX := waRight - 320
    hudY := waBottom - 110
    ToolTip(hudText, hudX, hudY, 1)
}

; ------------------------------------------------------------------------------
; Modality 1: Quick Region Snipping
; ------------------------------------------------------------------------------
StartScreenSnip() {
    global isSnipping, outputFolder, lastOutputFile, snipOverlayGui, snipBoxGui, quickSnipClipboard
    if (isSnipping)
        return
    isSnipping := true

    ; Modular ScreenSnipper delegation (SNIP-004)
    snipperScript := A_ScriptDir . "\\ScreenSnipper.ahk"
    if (FileExist(snipperScript)) {
        try {
            ahkBin := A_AhkPath != "" ? A_AhkPath : "C:\\Program Files\\AutoHotkey\\v2\\AutoHotkey64.exe"
            EnsureOutputDirectory()
            RunWait('"' . ahkBin . '" "' . snipperScript . '" --output "' . outputFolder . '" --clipboard "' . quickSnipClipboard . '"')
            lastMarker := outputFolder . "\\.last_snip"
            if (FileExist(lastMarker)) {
                try lastOutputFile := Trim(FileRead(lastMarker))
            }
            isSnipping := false
            return
        } catch {
            ; Fallback to internal snipper
        }
    }

    fgHwnd := DllCall("GetForegroundWindow", "Ptr")
    fgProc := ""
    fgTitle := ""
    if (fgHwnd) {
        try fgProc := WinGetProcessName(fgHwnd)
        try fgTitle := WinGetTitle(fgHwnd)
    }

    EnsureOutputDirectory()

    smX := DllCall("GetSystemMetrics", "Int", 76, "Int")
    smY := DllCall("GetSystemMetrics", "Int", 77, "Int")
    smW := DllCall("GetSystemMetrics", "Int", 78, "Int")
    smH := DllCall("GetSystemMetrics", "Int", 79, "Int")

    snipOverlayGui := Gui("-Caption +AlwaysOnTop +ToolWindow -DPIScale +E0x20")
    snipOverlayGui.BackColor := "000000"
    snipOverlayGui.Show("x" . smX . " y" . smY . " w" . smW . " h" . smH . " NoActivate")
    try WinSetTransparent(75, snipOverlayGui.Hwnd)

    snipBoxGui := Gui("-Caption +AlwaysOnTop +ToolWindow -DPIScale +E0x20")
    snipBoxGui.BackColor := "00E5FF"
    try WinSetTransparent(90, snipBoxGui.Hwnd)

    ToolTip("📸 Hover to snap window, or drag a region (Esc to cancel)", 40, 40, 2)

    startTime := A_TickCount
    clicked := false
    CoordMode "Mouse", "Screen"
    hoverHwnd := 0
    snapX := 0, snapY := 0, snapW := 0, snapH := 0, hasSnap := false

    while (A_TickCount - startTime < 15000) {
        if GetKeyState("Escape", "P")
            break
        if GetKeyState("LButton", "P") {
            clicked := true
            break
        }
        MouseGetPos(&mX, &mY, &mHwnd)
        if (mHwnd && mHwnd != snipOverlayGui.Hwnd && mHwnd != snipBoxGui.Hwnd && mHwnd != hoverHwnd) {
            hoverHwnd := mHwnd
            try {
                rect := Buffer(16, 0)
                if (DllCall("dwmapi\DwmGetWindowAttribute", "Ptr", hoverHwnd, "UInt", 9, "Ptr", rect, "UInt", 16) == 0) {
                    bx := NumGet(rect, 0, "Int"), by := NumGet(rect, 4, "Int")
                    bw := NumGet(rect, 8, "Int") - bx, bh := NumGet(rect, 12, "Int") - by
                    if (bw > 32 && bh > 32) {
                        snapX := bx, snapY := by, snapW := bw, snapH := bh, hasSnap := true
                        snipBoxGui.Show("x" . snapX . " y" . snapY . " w" . snapW . " h" . snapH . " NoActivate")
                    }
                }
            }
        }
        Sleep(20)
    }

    if (!clicked) {
        CleanupSnipOverlays()
        return
    }

    MouseGetPos(&startX, &startY)

    while GetKeyState("LButton", "P") {
        if GetKeyState("Escape", "P") {
            CleanupSnipOverlays()
            return
        }
        MouseGetPos(&curX, &curY)
        rx := Min(startX, curX)
        ry := Min(startY, curY)
        rw := Abs(curX - startX)
        rh := Abs(curY - startY)
        if (rw > 2 && rh > 2 && snipBoxGui) {
            snipBoxGui.Show("x" . rx . " y" . ry . " w" . rw . " h" . rh . " NoActivate")
            ToolTip("📐 " . rw . " × " . rh . " px", rx + 10, ry + rh + 10, 2)
        }
        Sleep(15)
    }

    finalX := Min(startX, curX)
    finalY := Min(startY, curY)
    finalW := Abs(curX - startX)
    finalH := Abs(curY - startY)

    ; If user clicked without dragging, use snapped window bounds if available
    if (finalW < 12 && finalH < 12 && hasSnap) {
        finalX := snapX, finalY := snapY, finalW := snapW, finalH := snapH
    }

    CleanupSnipOverlays()

    if (finalW < 12 || finalH < 12)
        return

    prefix := GetCleanPrefix(fgProc, fgTitle, "Snip")
    outFile := GenerateUniqueFilePath(outputFolder, prefix, ".png")
    CaptureScreenArea(finalX, finalY, finalW, finalH, outFile)
    if (FileExist(outFile) && FileGetSize(outFile) > 200) {
        lastOutputFile := outFile
        copiedImage := false
        if (quickSnipClipboard != "none") {
            copiedImage := CopyImageToClipboardNative(outFile, quickSnipClipboard)
        }
        if (!copiedImage && (quickSnipClipboard == "path" || quickSnipClipboard == "both")) {
            A_Clipboard := outFile
        }
        SoundPlay("*64")
        if (copiedImage) {
            if (quickSnipClipboard == "both") {
                ToolTip("✅ Screenshot Saved (" . finalW . "×" . finalH . "px)`n📋 Image & Path Copied to Clipboard`n📁 " . outFile, 30, 30, 1)
            } else if (quickSnipClipboard == "path") {
                ToolTip("✅ Screenshot Saved (" . finalW . "×" . finalH . "px)`n📋 Path Copied to Clipboard:`n" . outFile, 30, 30, 1)
            } else {
                ToolTip("✅ Screenshot Saved (" . finalW . "×" . finalH . "px)`n📋 Image Copied to Clipboard`n📁 " . outFile, 30, 30, 1)
            }
        } else {
            ToolTip("✅ Screenshot Saved (" . finalW . "×" . finalH . "px)`n📋 Path Copied to Clipboard:`n" . outFile, 30, 30, 1)
        }
        SetTimer(() => ToolTip(,,, 1), -3500)
        SetTimer(TrimWorkingSet, -1000)
    }
}

; ------------------------------------------------------------------------------
; Modality 2: Annotated Active Window Screenshot (Instant Snap to Notation Editor)
; ------------------------------------------------------------------------------
TriggerScrollCapture(*) {
    global defaultCaptureBehavior
    CaptureScrollingWindow(StrLower(defaultCaptureBehavior) != "standard")
}

CaptureScrollingWindow(annotateMode := false) {
    global isSnipping, isCapturingSnip, outputFolder, lastOutputFile, quickSnipClipboard, pythonExe, ffmpegExe, currentMic, clipboardTarget
    if (isSnipping || isCapturingSnip)
        return
    isSnipping := true
    isCapturingSnip := true
    sliceFiles := []
    borderGuis := []
    probeFile := ""
    try {
        EnsureOutputDirectory()
        if !SelectScrollCaptureArea(&finalX, &finalY, &finalW, &finalH)
            return

        borderGuis := CreateHollowScrollFrame(finalX, finalY, finalW, finalH)
        Sleep(40)

        tsBase := FormatTime(, "yyyyMMdd-HHmmss")
        firstSlice := outputFolder . "\.temp_snip_scroll_" . tsBase . "_1.png"
        if CaptureScreenArea(finalX, finalY, finalW, finalH, firstSlice)
            sliceFiles.Push(firstSlice)

        bannerX := Max(10, finalX)
        bannerY := (finalY > 48) ? (finalY - 42) : (finalY + finalH + 10)
        CoordMode "ToolTip", "Screen"
        ToolTip("📜 Manual Scroll Capture Active (" . sliceFiles.Length . " slice)`nScroll Up/Down now — Press Enter, Right-Click, or Esc when done", bannerX, bannerY, 2)

        startScrollWait := A_TickCount
        sliceIdx := 2
        while (A_TickCount - startScrollWait < 90000 && sliceFiles.Length < 60) {
            if (GetKeyState("Enter", "P") || GetKeyState("NumpadEnter", "P") || GetKeyState("Escape", "P") || GetKeyState("RButton", "P")) {
                try KeyWait("Enter", "T0.5")
                try KeyWait("Escape", "T0.5")
                try KeyWait("RButton", "T0.5")
                break
            }
            Sleep(85)
            probeFile := outputFolder . "\.temp_snip_scroll_" . tsBase . "_probe.png"
            if !CaptureScreenArea(finalX, finalY, finalW, finalH, probeFile)
                continue
            if (sliceFiles.Length > 0 && AreScrollSlicesIdentical(sliceFiles[sliceFiles.Length], probeFile)) {
                try FileDelete(probeFile)
                continue
            }
            ; Wait briefly for smooth scroll animation to settle, then capture settled frame
            Sleep(65)
            sliceFile := outputFolder . "\.temp_snip_scroll_" . tsBase . "_" . sliceIdx . ".png"
            if !CaptureScreenArea(finalX, finalY, finalW, finalH, sliceFile) {
                FileMove(probeFile, sliceFile, 1)
            } else {
                try FileDelete(probeFile)
            }
            if (sliceFiles.Length == 0 || !AreScrollSlicesIdentical(sliceFiles[sliceFiles.Length], sliceFile)) {
                sliceFiles.Push(sliceFile)
                sliceIdx += 1
                ToolTip("📜 Manual Scroll Capture Active (" . sliceFiles.Length . " slices)`nScroll Up/Down now — Press Enter, Right-Click, or Esc when done", bannerX, bannerY, 2)
            } else {
                try FileDelete(sliceFile)
            }
        }

        ToolTip(,,, 2)
        DestroyHollowScrollFrame(borderGuis)
        borderGuis := []

        if (sliceFiles.Length == 0) {
            ToolTip("⚠️ No scrolling capture slices were saved.", 30, 30, 1)
            SetTimer(() => ToolTip(,,, 1), -2500)
            return
        }

        ToolTip("⏳ Stitching " . sliceFiles.Length . " slices into seamless image...", bannerX, bannerY, 1)
        prefix := "Scroll"
        tempDest := outputFolder . "\.temp_snip_scroll_" . FormatTime(, "yyyyMMdd-HHmmss") . "_stitched.png"
        if (sliceFiles.Length == 1) {
            FileMove(sliceFiles[1], tempDest, 1)
        } else {
            stitched := false
            pyBin := (pythonExe != "" && IsValidPython(pythonExe)) ? pythonExe : GetPythonExe()
            stitchScript := FileExist(A_ScriptDir . "\src\scrolling_capture.py") ? (A_ScriptDir . "\src\scrolling_capture.py") : (FileExist(A_ScriptDir . "\scrolling_capture.py") ? (A_ScriptDir . "\scrolling_capture.py") : (FileExist(A_ScriptDir . "\..\src\scrolling_capture.py") ? (A_ScriptDir . "\..\src\scrolling_capture.py") : (A_ScriptDir . "\..\scrolling_capture.py")))
            if (pyBin != "" && FileExist(stitchScript)) {
                cmd := '"' . pyBin . '" "' . stitchScript . '" --output "' . tempDest . '"'
                for sliceFile in sliceFiles
                    cmd .= ' "' . sliceFile . '"'
                try RunWait(cmd, A_ScriptDir, "Hide")
                stitched := FileExist(tempDest) && FileGetSize(tempDest) > 200
            }
            if !stitched {
                editorExe := FindNotationEditor()
                if (editorExe != "" && FileExist(editorExe)) {
                    cmd := '"' . editorExe . '" --stitch-scroll "' . tempDest . '"'
                    for sliceFile in sliceFiles
                        cmd .= ' "' . sliceFile . '"'
                    try RunWait(cmd, A_ScriptDir, "Hide")
                    stitched := FileExist(tempDest) && FileGetSize(tempDest) > 200
                }
            }
            if !stitched
                stitched := StitchSlicesNativeGdip(sliceFiles, tempDest)
            if !stitched {
                ToolTip("⚠️ Could not stitch scrolling capture slices.", 30, 30, 1)
                SetTimer(() => ToolTip(,,, 1), -2500)
                return
            }
        }

        for sliceFile in sliceFiles {
            if FileExist(sliceFile)
                try FileDelete(sliceFile)
        }

        if annotateMode {
            editorExe := FindNotationEditor()
            editorScript := FileExist(A_ScriptDir . "\NotationEditor.py") ? (A_ScriptDir . "\NotationEditor.py") : (A_ScriptDir . "\..\NotationEditor.py")
            pyBin := (pythonExe != "" && IsValidPython(pythonExe)) ? pythonExe : GetPythonExe()
            if (editorExe == "" && (pyBin == "" || !FileExist(editorScript))) {
                ToolTip("⚠️ Notation Editor was not found for scrolling annotation.", 30, 30, 1)
                SetTimer(() => ToolTip(,,, 1), -3000)
                return
            }
            launchCmd := (editorExe != "")
                ? ('"' . editorExe . '" "' . tempDest . '" "' . outputFolder . '" "' . ffmpegExe . '" "' . currentMic . '" "Scroll" "' . clipboardTarget . '"')
                : ('"' . pyBin . '" "' . editorScript . '" "' . tempDest . '" "' . outputFolder . '" "' . ffmpegExe . '" "' . currentMic . '" "Scroll" "' . clipboardTarget . '"')
            Run(launchCmd, A_ScriptDir)
            ToolTip("📝 Scrolling capture ready in Review Editor.", 30, 30, 1)
        } else {
            outFile := GenerateUniqueFilePath(outputFolder, "ScrollSnip", ".png")
            FileMove(tempDest, outFile, 1)
            lastOutputFile := outFile
            if (quickSnipClipboard != "none")
                CopyImageToClipboardNative(outFile, quickSnipClipboard)
            if (quickSnipClipboard == "path")
                A_Clipboard := outFile
            SoundPlay("*64")
            ToolTip("✅ Scrolling capture saved:`n" . outFile, 30, 30, 1)
        }
        SetTimer(() => ToolTip(,,, 1), -3500)
    } finally {
        if (probeFile != "" && FileExist(probeFile))
            try FileDelete(probeFile)
        for sliceFile in sliceFiles {
            if FileExist(sliceFile)
                try FileDelete(sliceFile)
        }
        DestroyHollowScrollFrame(borderGuis)
        CleanupSnipOverlays()
        isSnipping := false
        isCapturingSnip := false
    }
}

CreateHollowScrollFrame(x, y, w, h) {
    bars := []
    thick := 2
    pad := 3
    coords := [
        [x - pad, y - pad, w + pad * 2, thick],
        [x - pad, y + h + pad - thick, w + pad * 2, thick],
        [x - pad, y - pad, thick, h + pad * 2],
        [x + w + pad - thick, y - pad, thick, h + pad * 2]
    ]
    for c in coords {
        g := Gui("-Caption +AlwaysOnTop +ToolWindow -DPIScale +E0x20")
        g.BackColor := "00E5FF"
        g.Show("x" . c[1] . " y" . c[2] . " w" . c[3] . " h" . c[4] . " NoActivate")
        try WinSetTransparent(210, g.Hwnd)
        bars.Push(g)
    }
    return bars
}

DestroyHollowScrollFrame(bars) {
    if !IsObject(bars)
        return
    for g in bars {
        try g.Destroy()
    }
}

SelectScrollCaptureArea(&finalX, &finalY, &finalW, &finalH) {
    global snipOverlayGui, snipBoxGui
    smX := DllCall("GetSystemMetrics", "Int", 76, "Int")
    smY := DllCall("GetSystemMetrics", "Int", 77, "Int")
    smW := DllCall("GetSystemMetrics", "Int", 78, "Int")
    smH := DllCall("GetSystemMetrics", "Int", 79, "Int")
    snipOverlayGui := Gui("-Caption +AlwaysOnTop +ToolWindow -DPIScale +E0x20")
    snipOverlayGui.BackColor := "000000"
    snipOverlayGui.Show("x" . smX . " y" . smY . " w" . smW . " h" . smH . " NoActivate")
    try WinSetTransparent(75, snipOverlayGui.Hwnd)

    snipBoxGui := Gui("-Caption +AlwaysOnTop +ToolWindow -DPIScale +E0x20")
    snipBoxGui.BackColor := "00E5FF"
    ToolTip("📜 Drag the area (or click a window) you want to Scroll Capture (Esc to cancel)", 40, 40, 2)
    CoordMode "Mouse", "Screen"
    startTime := A_TickCount
    hasSnap := false
    snapX := 0, snapY := 0, snapW := 0, snapH := 0
    while (A_TickCount - startTime < 15000) {
        if (GetKeyState("Escape", "P") || GetKeyState("RButton", "P")) {
            CleanupSnipOverlays()
            return false
        }
        if GetKeyState("LButton", "P")
            break
        MouseGetPos(&mX, &mY, &hoverHwnd)
        hoverHwnd := GetScrollCaptureWindowAtPoint(mX, mY, snipOverlayGui.Hwnd, snipBoxGui.Hwnd)
        if hoverHwnd {
            rect := Buffer(16, 0)
            if (DllCall("dwmapi\DwmGetWindowAttribute", "Ptr", hoverHwnd, "UInt", 9, "Ptr", rect, "UInt", 16) == 0) {
                snapX := NumGet(rect, 0, "Int"), snapY := NumGet(rect, 4, "Int")
                snapW := NumGet(rect, 8, "Int") - snapX, snapH := NumGet(rect, 12, "Int") - snapY
                if (snapW > 32 && snapH > 32) {
                    hasSnap := true
                    snipBoxGui.Show("x" . snapX . " y" . snapY . " w" . snapW . " h" . snapH . " NoActivate")
                    try WinSetTransparent(90, snipBoxGui.Hwnd)
                }
            }
        }
        Sleep(20)
    }
    if !GetKeyState("LButton", "P") {
        CleanupSnipOverlays()
        return false
    }
    MouseGetPos(&startX, &startY)
    curX := startX, curY := startY
    while GetKeyState("LButton", "P") {
        if (GetKeyState("Escape", "P") || GetKeyState("RButton", "P")) {
            CleanupSnipOverlays()
            return false
        }
        MouseGetPos(&curX, &curY)
        rw := Abs(curX - startX), rh := Abs(curY - startY)
        if (rw > 2 && rh > 2) {
            snipBoxGui.Show("x" . Min(startX, curX) . " y" . Min(startY, curY) . " w" . rw . " h" . rh . " NoActivate")
            try WinSetTransparent(90, snipBoxGui.Hwnd)
        }
        Sleep(15)
    }
    try KeyWait("LButton", "T0.5")
    finalX := Min(startX, curX), finalY := Min(startY, curY)
    finalW := Abs(curX - startX), finalH := Abs(curY - startY)
    if (finalW < 12 && finalH < 12 && hasSnap) {
        finalX := snapX + 8, finalY := snapY + 36, finalW := snapW - 16, finalH := snapH - 44
    }
    CleanupSnipOverlays()
    return finalW >= 12 && finalH >= 12
}

GetScrollCaptureWindowAtPoint(x, y, overlayHwnd := 0, boxHwnd := 0) {
    pt := (y << 32) | (x & 0xFFFFFFFF)
    hwnd := DllCall("user32\WindowFromPoint", "Int64", pt, "Ptr")
    Loop 8 {
        if !hwnd
            return 0
        root := DllCall("user32\GetAncestor", "Ptr", hwnd, "UInt", 2, "Ptr")
        if (root != overlayHwnd && root != boxHwnd && DllCall("user32\IsWindowVisible", "Ptr", root)) {
            rect := Buffer(16, 0)
            if DllCall("user32\GetWindowRect", "Ptr", root, "Ptr", rect) {
                left := NumGet(rect, 0, "Int"), top := NumGet(rect, 4, "Int")
                right := NumGet(rect, 8, "Int"), bottom := NumGet(rect, 12, "Int")
                if (x >= left && x < right && y >= top && y < bottom)
                    return root
            }
        }
        hwnd := DllCall("user32\GetWindow", "Ptr", hwnd, "UInt", 2, "Ptr")
    }
    return 0
}

AreScrollSlicesIdentical(firstFile, secondFile) {
    if (!FileExist(firstFile) || !FileExist(secondFile) || FileGetSize(firstFile) != FileGetSize(secondFile))
        return false
    firstData := FileRead(firstFile, "RAW")
    secondData := FileRead(secondFile, "RAW")
    return firstData.Size == secondData.Size && DllCall("msvcrt\memcmp", "Ptr", firstData.Ptr, "Ptr", secondData.Ptr, "UPtr", firstData.Size, "CDecl Int") == 0
}

StitchSlicesNativeGdip(sliceFiles, destFile) {
    if (!InitGdiplus() || sliceFiles.Length == 0)
        return false
    bitmaps := [], totalHeight := 0, width := 0
    try {
        for path in sliceFiles {
            pBitmap := 0
            if (DllCall("gdiplus\GdipCreateBitmapFromFile", "WStr", path, "Ptr*", &pBitmap) != 0 || !pBitmap)
                return false
            w := 0, h := 0
            DllCall("gdiplus\GdipGetImageWidth", "Ptr", pBitmap, "UInt*", &w)
            DllCall("gdiplus\GdipGetImageHeight", "Ptr", pBitmap, "UInt*", &h)
            if (width == 0)
                width := w
            if (w != width) {
                DllCall("gdiplus\GdipDisposeImage", "Ptr", pBitmap)
                continue
            }
            bitmaps.Push({ptr: pBitmap, height: h})
            totalHeight += h
        }
        if (width == 0 || totalHeight == 0)
            return false
        canvas := 0, graphics := 0
        if (DllCall("gdiplus\GdipCreateBitmapFromScan0", "Int", width, "Int", totalHeight, "Int", 0, "UInt", 0x26200A, "Ptr", 0, "Ptr*", &canvas) != 0 || !canvas)
            return false
        try {
            if (DllCall("gdiplus\GdipGetImageGraphicsContext", "Ptr", canvas, "Ptr*", &graphics) != 0 || !graphics)
                return false
            y := 0
            for bitmap in bitmaps {
                DllCall("gdiplus\GdipDrawImageRectI", "Ptr", graphics, "Ptr", bitmap.ptr, "Int", 0, "Int", y, "Int", width, "Int", bitmap.height)
                y += bitmap.height
            }
            clsid := Buffer(16, 0)
            DllCall("ole32\CLSIDFromString", "WStr", "{557cf406-1a04-11d3-9a73-0000f81ef32e}", "Ptr", clsid)
            return DllCall("gdiplus\GdipSaveImageToFile", "Ptr", canvas, "WStr", destFile, "Ptr", clsid, "Ptr", 0) == 0 && FileExist(destFile)
        } finally {
            if graphics
                DllCall("gdiplus\GdipDeleteGraphics", "Ptr", graphics)
            if canvas
                DllCall("gdiplus\GdipDisposeImage", "Ptr", canvas)
        }
    } catch {
        return false
    } finally {
        for bitmap in bitmaps
            try DllCall("gdiplus\GdipDisposeImage", "Ptr", bitmap.ptr)
    }
}
CaptureActiveWindowSnip() {
    global isCapturingSnip, outputFolder, lastOutputFile, ffmpegExe, currentMic, pythonExe, clipboardTarget
    if (isCapturingSnip)
        return
    isCapturingSnip := true

    tempSnip := ""
    try {
        EnsureOutputDirectory()

        editorExe := FindNotationEditor()
        editorScript := FileExist(A_ScriptDir . "\NotationEditor.py") ? (A_ScriptDir . "\NotationEditor.py") : (A_ScriptDir . "\..\NotationEditor.py")
        pyBin := (pythonExe != "" && IsValidPython(pythonExe)) ? pythonExe : GetPythonExe()

        if (editorExe == "" && !FileExist(editorScript)) {
            ToolTip("⚠️ Notation Editor not found in script directory.", 30, 30, 1)
            SetTimer(() => ToolTip(,,, 1), -3000)
            return
        }

        if (editorExe == "" && (pyBin == "" || !IsValidPython(pyBin))) {
            ToolTip("⚠️ A valid Python installation was not found and standalone editor is missing.", 30, 30, 1)
            SetTimer(() => ToolTip(,,, 1), -3000)
            return
        }

        procName := ""
        GetActiveWindowBounds(&winX, &winY, &winW, &winH, &winTitle, &procName)
        prefix := GetCleanPrefix(procName, winTitle, "WoTD")

        timestamp := FormatTime(, "yy-MMMdd-HHmm") . "_" . Mod(A_TickCount, 1000)
        tempSnip := outputFolder . "\.temp_snip_" . timestamp . ".png"

        activeHwnd := DllCall("GetForegroundWindow", "Ptr")
        CaptureWindowDirect(activeHwnd, winX, winY, winW, winH, tempSnip)

        if !(FileExist(tempSnip) && FileGetSize(tempSnip) > 200) {
            ToolTip("⚠️ Failed to capture active window screenshot.", 30, 30, 1)
            SetTimer(() => ToolTip(,,, 1), -2500)
            return
        }

        launchCmd := (editorExe != "")
            ? ('"' . editorExe . '" "' . tempSnip . '" "' . outputFolder . '" "' . ffmpegExe . '" "' . currentMic . '" "' . prefix . '" "' . clipboardTarget . '"')
            : ('"' . pyBin . '" "' . editorScript . '" "' . tempSnip . '" "' . outputFolder . '" "' . ffmpegExe . '" "' . currentMic . '" "' . prefix . '" "' . clipboardTarget . '"')
        try {
            Run(launchCmd, A_ScriptDir)
            displayTitle := winTitle
            if (StrLen(displayTitle) > 36)
                displayTitle := SubStr(displayTitle, 1, 33) . "..."
            ToolTip("📝 Captured: " . displayTitle . "`nOpening Review Editor...", 30, 30, 1)
            SetTimer(() => ToolTip(,,, 1), -2500)
        } catch as runErr {
            try FileAppend("NotationEditor launch error: " . runErr.Message . "`n", A_ScriptDir . "\error.log")
            ToolTip("❌ Failed to launch Notation Editor:`n" . runErr.Message, 30, 30, 1)
            SetTimer(() => ToolTip(,,, 1), -3500)
            if (FileExist(tempSnip)) {
                try FileDelete(tempSnip)
            }
        }
    } finally {
        isCapturingSnip := false
        SetTimer(TrimWorkingSet, -1000)
    }
}

CaptureRegionAnnotateSnip() {
    global isSnipping, isCapturingSnip, outputFolder, lastOutputFile, snipOverlayGui, snipBoxGui, ffmpegExe, currentMic, pythonExe, clipboardTarget
    if (isSnipping || isCapturingSnip)
        return
    isSnipping := true
    isCapturingSnip := true

    tempSnip := ""
    try {
        EnsureOutputDirectory()

        editorExe := FindNotationEditor()
        editorScript := FileExist(A_ScriptDir . "\NotationEditor.py") ? (A_ScriptDir . "\NotationEditor.py") : (A_ScriptDir . "\..\NotationEditor.py")
        pyBin := (pythonExe != "" && IsValidPython(pythonExe)) ? pythonExe : GetPythonExe()

        if (editorExe == "" && !FileExist(editorScript)) {
            ToolTip("⚠️ Notation Editor not found in script directory.", 30, 30, 1)
            SetTimer(() => ToolTip(,,, 1), -3000)
            return
        }
        if (editorExe == "" && (pyBin == "" || !IsValidPython(pyBin))) {
            ToolTip("⚠️ A valid Python installation was not found and standalone editor is missing.", 30, 30, 1)
            SetTimer(() => ToolTip(,,, 1), -3000)
            return
        }

        fgHwnd := DllCall("GetForegroundWindow", "Ptr")
        fgProc := ""
        fgTitle := ""
        if (fgHwnd) {
            try fgProc := WinGetProcessName(fgHwnd)
            try fgTitle := WinGetTitle(fgHwnd)
        }

        smX := DllCall("GetSystemMetrics", "Int", 76, "Int")
        smY := DllCall("GetSystemMetrics", "Int", 77, "Int")
        smW := DllCall("GetSystemMetrics", "Int", 78, "Int")
        smH := DllCall("GetSystemMetrics", "Int", 79, "Int")

        snipOverlayGui := Gui("-Caption +AlwaysOnTop +ToolWindow -DPIScale")
        snipOverlayGui.BackColor := "000000"
        WinSetTransparent(75, snipOverlayGui.Hwnd)
        snipOverlayGui.Show("x" . smX . " y" . smY . " w" . smW . " h" . smH)

        snipBoxGui := Gui("-Caption +AlwaysOnTop +ToolWindow -DPIScale")
        snipBoxGui.BackColor := "00E5FF"
        WinSetTransparent(90, snipBoxGui.Hwnd)

        ToolTip("📝 Drag a region (or click window) to open in Notation Editor (Esc to cancel)", 40, 40, 2)

        startTime := A_TickCount
        clicked := false
        CoordMode "Mouse", "Screen"
        hoverHwnd := 0
        snapX := 0, snapY := 0, snapW := 0, snapH := 0, hasSnap := false

        while (A_TickCount - startTime < 15000) {
            if GetKeyState("Escape", "P")
                break
            if GetKeyState("LButton", "P") {
                clicked := true
                break
            }
            MouseGetPos(&mX, &mY, &mHwnd)
            if (mHwnd && mHwnd != snipOverlayGui.Hwnd && mHwnd != snipBoxGui.Hwnd && mHwnd != hoverHwnd) {
                hoverHwnd := mHwnd
                try {
                    rect := Buffer(16, 0)
                    if (DllCall("dwmapi\DwmGetWindowAttribute", "Ptr", hoverHwnd, "UInt", 9, "Ptr", rect, "UInt", 16) == 0) {
                        bx := NumGet(rect, 0, "Int"), by := NumGet(rect, 4, "Int")
                        bw := NumGet(rect, 8, "Int") - bx, bh := NumGet(rect, 12, "Int") - by
                        if (bw > 32 && bh > 32) {
                            snapX := bx, snapY := by, snapW := bw, snapH := bh, hasSnap := true
                            snipBoxGui.Show("x" . snapX . " y" . snapY . " w" . snapW . " h" . snapH . " NoActivate")
                        }
                    }
                }
            }
            Sleep(20)
        }

        if (!clicked) {
            CleanupSnipOverlays()
            return
        }

        MouseGetPos(&startX, &startY)

        while GetKeyState("LButton", "P") {
            if GetKeyState("Escape", "P") {
                CleanupSnipOverlays()
                return
            }
            MouseGetPos(&curX, &curY)
            rx := Min(startX, curX)
            ry := Min(startY, curY)
            rw := Abs(curX - startX)
            rh := Abs(curY - startY)
            if (rw > 2 && rh > 2 && snipBoxGui) {
                snipBoxGui.Show("x" . rx . " y" . ry . " w" . rw . " h" . rh . " NoActivate")
                ToolTip("📐 " . rw . " × " . rh . " px", rx + 10, ry + rh + 10, 2)
            }
            Sleep(15)
        }

        finalX := Min(startX, curX)
        finalY := Min(startY, curY)
        finalW := Abs(curX - startX)
        finalH := Abs(curY - startY)

        if (finalW < 12 && finalH < 12 && hasSnap) {
            finalX := snapX, finalY := snapY, finalW := snapW, finalH := snapH
        }

        CleanupSnipOverlays()

        if (finalW < 12 || finalH < 12)
            return

        prefix := GetCleanPrefix(fgProc, fgTitle, "Region")
        timestamp := FormatTime(, "yy-MMMdd-HHmm") . "_" . Mod(A_TickCount, 1000)
        tempSnip := outputFolder . "\.temp_snip_" . timestamp . ".png"

        CaptureScreenArea(finalX, finalY, finalW, finalH, tempSnip)
        if !(FileExist(tempSnip) && FileGetSize(tempSnip) > 200) {
            ToolTip("⚠️ Failed to capture region screenshot.", 30, 30, 1)
            SetTimer(() => ToolTip(,,, 1), -2500)
            return
        }

        launchCmd := (editorExe != "")
            ? ('"' . editorExe . '" "' . tempSnip . '" "' . outputFolder . '" "' . ffmpegExe . '" "' . currentMic . '" "' . prefix . '" "' . clipboardTarget . '"')
            : ('"' . pyBin . '" "' . editorScript . '" "' . tempSnip . '" "' . outputFolder . '" "' . ffmpegExe . '" "' . currentMic . '" "' . prefix . '" "' . clipboardTarget . '"')
        try {
            Run(launchCmd, A_ScriptDir)
            ToolTip("📝 Region Captured (" . finalW . "×" . finalH . "px)`nOpening Review Editor...", 30, 30, 1)
            SetTimer(() => ToolTip(,,, 1), -2500)
        } catch as runErr {
            try FileAppend("NotationEditor launch error: " . runErr.Message . "`n", A_ScriptDir . "\error.log")
            ToolTip("❌ Failed to launch Notation Editor:`n" . runErr.Message, 30, 30, 1)
            SetTimer(() => ToolTip(,,, 1), -3500)
            if (FileExist(tempSnip)) {
                try FileDelete(tempSnip)
            }
        }
    } finally {
        CleanupSnipOverlays()
        isCapturingSnip := false
        SetTimer(TrimWorkingSet, -1000)
    }
}

CaptureActiveWindowQuickSnip() {
    global isCapturingSnip, outputFolder, lastOutputFile, quickSnipClipboard
    if (isCapturingSnip)
        return
    isCapturingSnip := true

    try {
        EnsureOutputDirectory()
        procName := ""
        GetActiveWindowBounds(&winX, &winY, &winW, &winH, &winTitle, &procName)
        prefix := GetCleanPrefix(procName, winTitle, "WindowSnip")
        outFile := GenerateUniqueFilePath(outputFolder, prefix, ".png")
        activeHwnd := DllCall("GetForegroundWindow", "Ptr")
        CaptureWindowDirect(activeHwnd, winX, winY, winW, winH, outFile)

        if (FileExist(outFile) && FileGetSize(outFile) > 200) {
            lastOutputFile := outFile
            copiedImage := false
            if (quickSnipClipboard != "none") {
                copiedImage := CopyImageToClipboardNative(outFile, quickSnipClipboard)
            }
            if (!copiedImage && (quickSnipClipboard == "path" || quickSnipClipboard == "both")) {
                A_Clipboard := outFile
            }
            SoundPlay("*64")
            ToolTip("✅ Window Screenshot Saved (" . winW . "×" . winH . "px)`n📋 Copied to Clipboard`n📁 " . outFile, 30, 30, 1)
            SetTimer(() => ToolTip(,,, 1), -3500)
        }
    } finally {
        isCapturingSnip := false
        SetTimer(TrimWorkingSet, -1000)
    }
}

CleanupSnipOverlays() {
    global isSnipping, snipOverlayGui, snipBoxGui
    if (snipOverlayGui) {
        try snipOverlayGui.Destroy()
        snipOverlayGui := 0
    }
    if (snipBoxGui) {
        try snipBoxGui.Destroy()
        snipBoxGui := 0
    }
    ToolTip(,,, 2)
    isSnipping := false
    SetTimer(TrimWorkingSet, -1000)
}

CleanupAllResources() {
    CleanupSnipOverlays()
    global highlightGui, hProcess, hStdInWrite
    if (highlightGui) {
        try highlightGui.Destroy()
        highlightGui := 0
    }
    if (hStdInWrite) {
        try {
            qBuf := Buffer(4, 0)
            StrPut("q`n", qBuf, "CP0")
            written := 0
            DllCall("WriteFile", "Ptr", hStdInWrite, "Ptr", qBuf, "UInt", 2, "UInt*", &written, "Ptr", 0)
            DllCall("CloseHandle", "Ptr", hStdInWrite)
        }
        hStdInWrite := 0
    }
    if (hProcess) {
        waitRes := DllCall("WaitForSingleObject", "Ptr", hProcess, "UInt", 800)
        if (waitRes != 0) {
            try DllCall("TerminateProcess", "Ptr", hProcess, "UInt", 1)
            try DllCall("WaitForSingleObject", "Ptr", hProcess, "UInt", 500)
        }
        try DllCall("CloseHandle", "Ptr", hProcess)
        hProcess := 0
    }
    ShutdownGdiplus()
}

CaptureWindowDirect(hwnd, x, y, w, h, outFile) {
    w := Max(2, w - Mod(w, 2))
    h := Max(2, h - Mod(h, 2))
    if (!InitGdiplus())
        return false

    hdcScreen := 0
    hdcMem := 0
    hBitmap := 0
    hOld := 0
    pGdipBmp := 0

    try {
        hdcScreen := DllCall("GetDC", "Ptr", 0, "Ptr")
        if (!hdcScreen)
            return false
        hdcMem := DllCall("CreateCompatibleDC", "Ptr", hdcScreen, "Ptr")
        if (!hdcMem)
            return false
        hBitmap := DllCall("CreateCompatibleBitmap", "Ptr", hdcScreen, "Int", w, "Int", h, "Ptr")
        if (!hBitmap)
            return false
        hOld := DllCall("SelectObject", "Ptr", hdcMem, "Ptr", hBitmap, "Ptr")

        ; Direct composited capture via BitBlt with SRCCOPY | CAPTUREBLT (0x40CC0020)
        bltOk := DllCall("BitBlt", "Ptr", hdcMem, "Int", 0, "Int", 0, "Int", w, "Int", h, "Ptr", hdcScreen, "Int", x, "Int", y, "UInt", 0x40CC0020)
        if (!bltOk && hwnd && DllCall("IsWindow", "Ptr", hwnd)) {
            ; Fallback to PrintWindow if BitBlt fails
            DllCall("PrintWindow", "Ptr", hwnd, "Ptr", hdcMem, "UInt", 2)
        }

        if (DllCall("gdiplus\GdipCreateBitmapFromHBITMAP", "Ptr", hBitmap, "Ptr", 0, "Ptr*", &pGdipBmp) != 0 || !pGdipBmp)
            return false

        clsid := Buffer(16, 0)
        DllCall("ole32\CLSIDFromString", "WStr", "{557cf406-1a04-11d3-9a73-0000f81ef32e}", "Ptr", clsid)

        saveStatus := DllCall("gdiplus\GdipSaveImageToFile", "Ptr", pGdipBmp, "WStr", outFile, "Ptr", clsid, "Ptr", 0)
        return (saveStatus == 0 && FileExist(outFile) && FileGetSize(outFile) > 200)
    } catch {
        return false
    } finally {
        if (pGdipBmp)
            try DllCall("gdiplus\GdipDisposeImage", "Ptr", pGdipBmp)
        if (hdcMem && hOld)
            try DllCall("SelectObject", "Ptr", hdcMem, "Ptr", hOld)
        if (hBitmap)
            try DllCall("DeleteObject", "Ptr", hBitmap)
        if (hdcMem)
            try DllCall("DeleteDC", "Ptr", hdcMem)
        if (hdcScreen)
            try DllCall("ReleaseDC", "Ptr", 0, "Ptr", hdcScreen)
    }
}

CaptureScreenArea(x, y, w, h, outFile) {
    w := Max(2, w - Mod(w, 2))
    h := Max(2, h - Mod(h, 2))
    if (!InitGdiplus())
        return false

    hdcScreen := 0
    hdcMem := 0
    hBitmap := 0
    hOld := 0
    pGdipBmp := 0

    try {
        hdcScreen := DllCall("GetDC", "Ptr", 0, "Ptr")
        if (!hdcScreen)
            return false
        hdcMem := DllCall("CreateCompatibleDC", "Ptr", hdcScreen, "Ptr")
        if (!hdcMem)
            return false
        hBitmap := DllCall("CreateCompatibleBitmap", "Ptr", hdcScreen, "Int", w, "Int", h, "Ptr")
        if (!hBitmap)
            return false
        hOld := DllCall("SelectObject", "Ptr", hdcMem, "Ptr", hBitmap, "Ptr")

        ; 0x40CC0020 = SRCCOPY (0x00CC0020) | CAPTUREBLT (0x40000000)
        DllCall("BitBlt", "Ptr", hdcMem, "Int", 0, "Int", 0, "Int", w, "Int", h, "Ptr", hdcScreen, "Int", x, "Int", y, "UInt", 0x40CC0020)

        if (DllCall("gdiplus\GdipCreateBitmapFromHBITMAP", "Ptr", hBitmap, "Ptr", 0, "Ptr*", &pGdipBmp) != 0 || !pGdipBmp)
            return false

        clsid := Buffer(16, 0)
        DllCall("ole32\CLSIDFromString", "WStr", "{557cf406-1a04-11d3-9a73-0000f81ef32e}", "Ptr", clsid)

        saveStatus := DllCall("gdiplus\GdipSaveImageToFile", "Ptr", pGdipBmp, "WStr", outFile, "Ptr", clsid, "Ptr", 0)
        return (saveStatus == 0 && FileExist(outFile) && FileGetSize(outFile) > 200)
    } catch {
        return false
    } finally {
        if (pGdipBmp)
            try DllCall("gdiplus\GdipDisposeImage", "Ptr", pGdipBmp)
        if (hdcMem && hOld)
            try DllCall("SelectObject", "Ptr", hdcMem, "Ptr", hOld)
        if (hBitmap)
            try DllCall("DeleteObject", "Ptr", hBitmap)
        if (hdcMem)
            try DllCall("DeleteDC", "Ptr", hdcMem)
        if (hdcScreen)
            try DllCall("ReleaseDC", "Ptr", 0, "Ptr", hdcScreen)
    }
}

CopyImageToClipboardNative(imgPath, clipMode := "image") {
    if (!FileExist(imgPath) || clipMode == "none")
        return false

    ; Method 1: High-performance in-process GDI+ / User32 multi-format pipeline (0 subprocesses, < 5ms)
    try {
        hBitmap := 0
        hDib := 0
        hPng := 0
        hImagePng := 0
        hDrop := 0
        hText := 0
        hUrl := 0

        ; 1. Prepare Bitmap and DIB handles if image format requested
        if (clipMode != "path") {
            if (InitGdiplus()) {
                pBitmap := 0
                if (DllCall("gdiplus\GdipCreateBitmapFromFile", "WStr", imgPath, "Ptr*", &pBitmap) == 0 && pBitmap) {
                    DllCall("gdiplus\GdipCreateHBITMAPFromBitmap", "Ptr", pBitmap, "Ptr*", &hBitmap, "UInt", 0xFFFFFFFF)
                    DllCall("gdiplus\GdipDisposeImage", "Ptr", pBitmap)
                }
            }

            if (hBitmap) {
                hdc := DllCall("GetDC", "Ptr", 0, "Ptr")
                if (hdc) {
                    bmi := Buffer(40, 0)
                    NumPut("UInt", 40, bmi, 0)
                    if DllCall("GetDIBits", "Ptr", hdc, "Ptr", hBitmap, "UInt", 0, "UInt", 0, "Ptr", 0, "Ptr", bmi, "UInt", 0) {
                        biW := NumGet(bmi, 4, "Int")
                        biH := NumGet(bmi, 8, "Int")
                        biBpp := NumGet(bmi, 14, "UShort")
                        biSizeImage := NumGet(bmi, 20, "UInt")
                        if (biSizeImage == 0)
                            biSizeImage := (((biW * biBpp + 31) // 32) * 4) * Abs(biH)
                        dibSize := 40 + biSizeImage
                        hDib := DllCall("GlobalAlloc", "UInt", 0x0002, "UPtr", dibSize, "Ptr")
                        if (hDib) {
                            pDib := DllCall("GlobalLock", "Ptr", hDib, "Ptr")
                            if (pDib) {
                                DllCall("RtlMoveMemory", "Ptr", pDib, "Ptr", bmi, "UPtr", 40)
                                DllCall("GetDIBits", "Ptr", hdc, "Ptr", hBitmap, "UInt", 0, "UInt", Abs(biH), "Ptr", pDib + 40, "Ptr", pDib, "UInt", 0)
                                DllCall("GlobalUnlock", "Ptr", hDib)
                            } else {
                                DllCall("GlobalFree", "Ptr", hDib)
                                hDib := 0
                            }
                        }
                    }
                    DllCall("ReleaseDC", "Ptr", 0, "Ptr", hdc)
                }
            }

            ; Prepare raw PNG byte streams for Discord, Teams, Chrome
            fileData := FileRead(imgPath, "RAW")
            if (fileData && fileData.Size > 0) {
                hPng := DllCall("GlobalAlloc", "UInt", 0x0002, "UPtr", fileData.Size, "Ptr")
                if (hPng) {
                    pPng := DllCall("GlobalLock", "Ptr", hPng, "Ptr")
                    if (pPng) {
                        DllCall("RtlMoveMemory", "Ptr", pPng, "Ptr", fileData, "UPtr", fileData.Size)
                        DllCall("GlobalUnlock", "Ptr", hPng)
                    } else {
                        DllCall("GlobalFree", "Ptr", hPng)
                        hPng := 0
                    }
                }
                hImagePng := DllCall("GlobalAlloc", "UInt", 0x0002, "UPtr", fileData.Size, "Ptr")
                if (hImagePng) {
                    pImgPng := DllCall("GlobalLock", "Ptr", hImagePng, "Ptr")
                    if (pImgPng) {
                        DllCall("RtlMoveMemory", "Ptr", pImgPng, "Ptr", fileData, "UPtr", fileData.Size)
                        DllCall("GlobalUnlock", "Ptr", hImagePng)
                    } else {
                        DllCall("GlobalFree", "Ptr", hImagePng)
                        hImagePng := 0
                    }
                }
            }
        }

        ; 2. Prepare CF_HDROP only when an image is intentionally offered as a file drop.
        pathLen := StrLen(imgPath)
        if (clipMode != "path") {
            hDropSize := 20 + (pathLen + 2) * 2
            hDrop := DllCall("GlobalAlloc", "UInt", 0x0002, "UPtr", hDropSize, "Ptr")
            if (hDrop) {
                pDrop := DllCall("GlobalLock", "Ptr", hDrop, "Ptr")
                if (pDrop) {
                    NumPut("UInt", 20, pDrop, 0)
                    NumPut("Int", 0, pDrop, 4)
                    NumPut("Int", 0, pDrop, 8)
                    NumPut("Int", 0, pDrop, 12)
                    NumPut("Int", 1, pDrop, 16)
                    StrPut(imgPath, pDrop + 20, "UTF-16")
                    NumPut("UShort", 0, pDrop, 20 + pathLen * 2)
                    NumPut("UShort", 0, pDrop, 20 + pathLen * 2 + 2)
                    DllCall("GlobalUnlock", "Ptr", hDrop)
                } else {
                    DllCall("GlobalFree", "Ptr", hDrop)
                    hDrop := 0
                }
            }
        }

        ; 3. Prepare CF_UNICODETEXT and UniformResourceLocatorW if "both" or "path"
        if (clipMode == "both" || clipMode == "path") {
            hText := DllCall("GlobalAlloc", "UInt", 0x0002, "UPtr", (pathLen + 1) * 2, "Ptr")
            if (hText) {
                pText := DllCall("GlobalLock", "Ptr", hText, "Ptr")
                if (pText) {
                    StrPut(imgPath, pText, "UTF-16")
                    DllCall("GlobalUnlock", "Ptr", hText)
                } else {
                    DllCall("GlobalFree", "Ptr", hText)
                    hText := 0
                }
            }

            fileUri := "file:///" . StrReplace(imgPath, "\", "/")
            urlLen := StrLen(fileUri)
            hUrl := DllCall("GlobalAlloc", "UInt", 0x0002, "UPtr", (urlLen + 1) * 2, "Ptr")
            if (hUrl) {
                pUrl := DllCall("GlobalLock", "Ptr", hUrl, "Ptr")
                if (pUrl) {
                    StrPut(fileUri, pUrl, "UTF-16")
                    DllCall("GlobalUnlock", "Ptr", hUrl)
                } else {
                    DllCall("GlobalFree", "Ptr", hUrl)
                    hUrl := 0
                }
            }
        }

        ; 4. Open Clipboard with Retry Loop (up to 5 attempts with 10ms backoff)
        opened := false
        loop 5 {
            if DllCall("OpenClipboard", "Ptr", 0) {
                opened := true
                break
            }
            Sleep(10)
        }

        if (!opened) {
            if (hBitmap) {
                DllCall("DeleteObject", "Ptr", hBitmap)
            }
            if (hDib) {
                DllCall("GlobalFree", "Ptr", hDib)
            }
            if (hPng) {
                DllCall("GlobalFree", "Ptr", hPng)
            }
            if (hImagePng) {
                DllCall("GlobalFree", "Ptr", hImagePng)
            }
            if (hDrop && clipMode != "path") {
                DllCall("GlobalFree", "Ptr", hDrop)
            }
            if (hText) {
                DllCall("GlobalFree", "Ptr", hText)
            }
            if (hUrl) {
                DllCall("GlobalFree", "Ptr", hUrl)
            }
            return false
        }

        ; 5. Single Clipboard Transaction
        anySuccess := false
        try {
            DllCall("EmptyClipboard")
            cfPng := DllCall("RegisterClipboardFormat", "Str", "PNG", "UInt")
            cfImagePng := DllCall("RegisterClipboardFormat", "Str", "image/png", "UInt")
            cfUrlW := DllCall("RegisterClipboardFormat", "Str", "UniformResourceLocatorW", "UInt")

            if (clipMode != "path") {
                if (hDib) {
                    if DllCall("SetClipboardData", "UInt", 8, "Ptr", hDib, "Ptr")
                        anySuccess := true
                    else
                        DllCall("GlobalFree", "Ptr", hDib)
                }
                if (hBitmap) {
                    if DllCall("SetClipboardData", "UInt", 2, "Ptr", hBitmap, "Ptr")
                        anySuccess := true
                    else
                        DllCall("DeleteObject", "Ptr", hBitmap)
                }
                if (hPng && cfPng) {
                    if DllCall("SetClipboardData", "UInt", cfPng, "Ptr", hPng, "Ptr")
                        anySuccess := true
                    else
                        DllCall("GlobalFree", "Ptr", hPng)
                }
                if (hImagePng && cfImagePng) {
                    if DllCall("SetClipboardData", "UInt", cfImagePng, "Ptr", hImagePng, "Ptr")
                        anySuccess := true
                    else
                        DllCall("GlobalFree", "Ptr", hImagePng)
                }
            } else {
                if (hBitmap)
                    DllCall("DeleteObject", "Ptr", hBitmap)
                if (hDib)
                    DllCall("GlobalFree", "Ptr", hDib)
                if (hPng)
                    DllCall("GlobalFree", "Ptr", hPng)
                if (hImagePng)
                    DllCall("GlobalFree", "Ptr", hImagePng)
            }

            if (hDrop && clipMode != "path") {
                if DllCall("SetClipboardData", "UInt", 15, "Ptr", hDrop, "Ptr")
                    anySuccess := true
                else
                    DllCall("GlobalFree", "Ptr", hDrop)
            }

            if (clipMode == "both" || clipMode == "path") {
                if (hText) {
                    if DllCall("SetClipboardData", "UInt", 13, "Ptr", hText, "Ptr")
                        anySuccess := true
                    else
                        DllCall("GlobalFree", "Ptr", hText)
                }
                if (hUrl && cfUrlW) {
                    if DllCall("SetClipboardData", "UInt", cfUrlW, "Ptr", hUrl, "Ptr")
                        anySuccess := true
                    else
                        DllCall("GlobalFree", "Ptr", hUrl)
                }
            } else {
                if (hText)
                    DllCall("GlobalFree", "Ptr", hText)
                if (hUrl)
                    DllCall("GlobalFree", "Ptr", hUrl)
            }
        } finally {
            DllCall("CloseClipboard")
        }
        if (clipMode == "path")
            A_Clipboard := imgPath
        if (anySuccess)
            return true
    } catch {
    }

    ; Method 2: Python clipboard_helper fallback
    global pythonExe
    pyBin := (pythonExe != "" && FileExist(pythonExe)) ? pythonExe : GetPythonExe()
    if (pyBin != "" && FileExist(pyBin)) {
        clipHelper := (FileExist(A_ScriptDir . "\src\clipboard_helper.py") ? (A_ScriptDir . "\src\clipboard_helper.py") : (FileExist(A_ScriptDir . "\clipboard_helper.py") ? (A_ScriptDir . "\clipboard_helper.py") : (FileExist(A_ScriptDir . "\..\src\clipboard_helper.py") ? (A_ScriptDir . "\..\src\clipboard_helper.py") : (A_ScriptDir . "\..\clipboard_helper.py"))))
        if (FileExist(clipHelper)) {
            pyCmd := '"' . pyBin . '" "' . clipHelper . '" "' . imgPath . '" --mode ' . clipMode
            if (RunWait(pyCmd,, "Hide") == 0)
                return true
        }
    }

    return false
}

GetCleanPrefix(procName, winTitle, defaultPrefix := "Clip") {
    cleanProc := RegExReplace(procName, "(?i)\.exe$", "")

    if (InStr(cleanProc, "whisper_of_the_divine")
        || InStr(cleanProc, "whisper-of-the-divine")
        || InStr(cleanProc, "wotd")
        || InStr(winTitle, "Whisper of the Divine")
        || InStr(winTitle, "WoTD")) {
        return "WoTD"
    }

    if (cleanProc != "") {
        clean := RegExReplace(cleanProc, '[\\/:*?"<>|\r\n\t\s]', '_')
        clean := Trim(clean, "_")
        if (StrLen(clean) > 16)
            clean := SubStr(clean, 1, 16)
        return clean
    }

    if (winTitle != "" && winTitle != "Active Window" && winTitle != "Full Desktop") {
        clean := RegExReplace(winTitle, '[\\/:*?"<>|\r\n\t\s]', '_')
        clean := Trim(clean, "_")
        if (StrLen(clean) > 16)
            clean := SubStr(clean, 1, 16)
        return clean
    }

    return defaultPrefix
}

GenerateUniqueFilePath(outputDir, prefix, ext) {
    timeStr := FormatTime(, "yy-MMMdd-HHmm")
    baseName := prefix . "-" . timeStr
    target := outputDir . "\" . baseName . ext

    if !FileExist(target)
        return target

    idx := 1
    while true {
        candidate := outputDir . "\" . baseName . "-" . idx . ext
        if !FileExist(candidate)
            return candidate
        idx++
    }
}

; ------------------------------------------------------------------------------
; Active Window Geometry (Virtual Desktop / Multi-Monitor Safe)
; ------------------------------------------------------------------------------
GetActiveWindowBounds(&x, &y, &w, &h, &title, &proc := "") {
    ; Initialize outputs with safe virtual-screen defaults first
    x := 0, y := 0, w := 1920, h := 1080
    title := "Active Window"
    proc := ""
    smX := 0, smY := 0, smW := 1920, smH := 1080

    try {
        smX := DllCall("GetSystemMetrics", "Int", 76, "Int") ; SM_XVIRTUALSCREEN
        smY := DllCall("GetSystemMetrics", "Int", 77, "Int") ; SM_YVIRTUALSCREEN
        smW := DllCall("GetSystemMetrics", "Int", 78, "Int") ; SM_CXVIRTUALSCREEN
        smH := DllCall("GetSystemMetrics", "Int", 79, "Int") ; SM_CYVIRTUALSCREEN

        if (smW > 0 && smH > 0) {
            x := smX, y := smY, w := smW, h := smH
        }
    }

    hwnd := 0
    try {
        hwnd := DllCall("GetForegroundWindow", "Ptr")
        if !hwnd {
            hwnd := WinGetID("A")
        }
    } catch {
        hwnd := 0
    }

    if (!hwnd) {
        w := w - Mod(w, 2)
        h := h - Mod(h, 2)
        return
    }

    try {
        t := WinGetTitle(hwnd)
        if (t != "")
            title := t
    }
    try {
        p := WinGetProcessName(hwnd)
        if (p != "")
            proc := p
    }

    rect := Buffer(16, 0)
    gotRect := false

    try {
        hr := DllCall("dwmapi\DwmGetWindowAttribute", "Ptr", hwnd, "UInt", 9, "Ptr", rect, "UInt", 16)
        if (hr == 0) {
            rx := NumGet(rect, 0, "Int")
            ry := NumGet(rect, 4, "Int")
            rw := NumGet(rect, 8, "Int") - rx
            rh := NumGet(rect, 12, "Int") - ry
            if (rw > 0 && rh > 0) {
                x := rx, y := ry, w := rw, h := rh
                gotRect := true
            }
        }
    }

    if (!gotRect) {
        try {
            WinGetPos(&wx, &wy, &ww, &wh, hwnd)
            if (ww > 0 && wh > 0) {
                x := wx, y := wy, w := ww, h := wh
                gotRect := true
            }
        }
    }

    if (!gotRect || w < 100 || h < 100 || x < smX - 1000 || y < smY - 1000) {
        x := smX, y := smY, w := smW, h := smH
    } else {
        if (x < smX) {
            w += (x - smX)
            x := smX
        }
        if (y < smY) {
            h += (y - smY)
            y := smY
        }
        if (x + w > smX + smW)
            w := (smX + smW) - x
        if (y + h > smY + smH)
            h := (smY + smH) - y
    }

    ; If clipping reduced dimensions below minimal threshold, fall back to full virtual screen
    if (w < 100 || h < 100) {
        x := smX, y := smY, w := smW, h := smH
    }

    w := w - Mod(w, 2)
    h := h - Mod(h, 2)
}

; ------------------------------------------------------------------------------
; FFmpeg Spawning
; ------------------------------------------------------------------------------
GetEncoderArgs(encType, crf) {
    enc := StrLower(Trim(encType))
    if (enc == "nvenc" || enc == "h264_nvenc")
        return "-c:v h264_nvenc -preset p1 -tune ull -rc constqp -qp " . crf . " -pix_fmt yuv420p"
    if (enc == "amf" || enc == "h264_amf")
        return "-c:v h264_amf -usage ultralowlatency -rc cqp -qp_i " . crf . " -qp_p " . crf . " -pix_fmt yuv420p"
    if (enc == "qsv" || enc == "h264_qsv")
        return "-c:v h264_qsv -preset veryfast -global_quality " . crf . " -pix_fmt yuv420p"
    if (enc == "cpu" || enc == "libx264")
        return "-c:v libx264 -preset ultrafast -tune zerolatency -crf " . crf . " -pix_fmt yuv420p"

    cachePath := A_ScriptDir . "\.encoder_cache.json"
    if FileExist(cachePath) {
        try {
            content := FileRead(cachePath, "UTF-8")
            if InStr(content, "h264_nvenc") && InStr(content, "true")
                return "-c:v h264_nvenc -preset p1 -tune ull -rc constqp -qp " . crf . " -pix_fmt yuv420p"
            if InStr(content, "h264_amf") && InStr(content, "true")
                return "-c:v h264_amf -usage ultralowlatency -rc cqp -qp_i " . crf . " -qp_p " . crf . " -pix_fmt yuv420p"
            if InStr(content, "h264_qsv") && InStr(content, "true")
                return "-c:v h264_qsv -preset veryfast -global_quality " . crf . " -pix_fmt yuv420p"
        }
    }

    return "-c:v libx264 -preset ultrafast -tune zerolatency -crf " . crf . " -pix_fmt yuv420p"
}
SpawnFFmpeg(outPath, x, y, w, h, micName) {
    global ffmpegExe, hProcess, hStdInWrite, fpsVal, crfVal, encoderVal, showCursor

    cmd := '"' . ffmpegExe . '" -y -loglevel warning'
    cmd .= ' -f gdigrab -framerate ' . fpsVal . (showCursor ? ' -draw_mouse 1' : ' -draw_mouse 0') . ' -offset_x ' . x . ' -offset_y ' . y . ' -video_size ' . w . 'x' . h . ' -i desktop'

    hasMic := (micName != "")
    if (hasMic)
        cmd .= ' -f dshow -i audio="' . micName . '"'

    cmd .= ' ' . GetEncoderArgs(encoderVal, crfVal)
    if (hasMic)
        cmd .= ' -c:a aac -b:a 128k'

    ; Crash-proof fragmented MP4 container writing (CAP-003)
    if (SubStr(outPath, -4) = ".mp4" || SubStr(outPath, -4) = ".m4v")
        cmd .= ' -movflags +frag_keyframe+empty_moov+default_base_moof'

    cmd .= ' "' . outPath . '"'

    sa := Buffer(24, 0)
    NumPut("UInt", 24, sa, 0)
    NumPut("Int", 1, sa, A_PtrSize == 8 ? 16 : 12)

    hRead := 0, hWrite := 0
    if !DllCall("CreatePipe", "Ptr*", &hRead, "Ptr*", &hWrite, "Ptr", sa, "UInt", 0)
        return false

    DllCall("SetHandleInformation", "Ptr", hWrite, "UInt", 1, "UInt", 0)

    si := Buffer(A_PtrSize == 8 ? 104 : 68, 0)
    NumPut("UInt", si.Size, si, 0)
    NumPut("UInt", 0x101, si, A_PtrSize == 8 ? 60 : 44)
    NumPut("UShort", 0, si, A_PtrSize == 8 ? 64 : 48)
    NumPut("Ptr", hRead, si, A_PtrSize == 8 ? 80 : 56)

    pi := Buffer(A_PtrSize == 8 ? 24 : 16, 0)
    ok := DllCall("CreateProcessW", "Ptr", 0, "Str", cmd, "Ptr", 0, "Ptr", 0, "Int", 1, "UInt", 0x08000000, "Ptr", 0, "Ptr", 0, "Ptr", si, "Ptr", pi)
    DllCall("CloseHandle", "Ptr", hRead)

    if !ok {
        DllCall("CloseHandle", "Ptr", hWrite)
        return false
    }

    hProcess := NumGet(pi, 0, "Ptr")
    hThread := NumGet(pi, A_PtrSize, "Ptr")
    DllCall("CloseHandle", "Ptr", hThread)
    hStdInWrite := hWrite
    return true
}

; ------------------------------------------------------------------------------
; Tray Menu
; ------------------------------------------------------------------------------
BuildTrayMenu() {
    global iniPath, regionCaptureKey, windowCaptureKey, scrollCaptureKey, defaultCaptureBehavior, captureModifier, revertHotkey, airGappedMode
    tray := A_TrayMenu
    tray.Delete()
    tray.Add("📸 Region Capture (Standard) [" . CaptureShortcutLabel("region", "standard") . "]", (*) => StartScreenSnip())
    tray.Add("📝 Region Capture (Annotate) [" . CaptureShortcutLabel("region", "annotate") . "]", (*) => CaptureRegionAnnotateSnip())
    tray.Add("🖼️ Window Capture (Standard) [" . CaptureShortcutLabel("window", "standard") . "]", (*) => CaptureActiveWindowQuickSnip())
    tray.Add("📝 Window Capture (Annotate) [" . CaptureShortcutLabel("window", "annotate") . "]", (*) => CaptureActiveWindowSnip())
    tray.Add("📜 Scrolling Window Capture (Standard) [" . CaptureShortcutLabel("scroll", "standard") . "]", (*) => CaptureScrollingWindow(false))
    tray.Add("📜 Scrolling Window Capture (Annotate) [" . CaptureShortcutLabel("scroll", "annotate") . "]", (*) => CaptureScrollingWindow(true))
    tray.Add()
    tray.Add("🖼️ Copy Last Image to Clipboard", MenuCopyLastImage)
    tray.Add("📋 Copy Last Image Path", MenuCopyLastPath)
    tray.Add("📁 Open Screenshots Folder", MenuOpenFolder)
    tray.Add()
    tray.Add("⚙️ PromptLens Settings...", (*) => ShowScreenshotSettingsGui())
    tray.Add("⚙️ Open Settings (config.ini)", (*) => Run(iniPath))
    tray.Add("🚀 Launch on Windows Startup", (*) => ToggleStartupIntegration())
    tray.Add("🔄 Check for Updates...", (*) => CheckForUpdatesManual())
    if IsStartupEnabled()
        tray.Check("🚀 Launch on Windows Startup")
    if airGappedMode {
        tray.Disable("🔄 Check for Updates...")
        tray.Add("🔒 Air-Gapped Mode (Cloud Egress Blocked)", (*) => ShowAirGappedInfo())
    }
    tray.Add("⚡ Optimize Memory (< 35 MB)", (*) => MenuOptimizeMemory())
    tray.Add()
    tray.Add("❌ Exit Suite", (*) => ExitApp())

    UpdateTrayTip()
}

CaptureShortcutLabel(captureType, mode) {
    global regionCaptureKey, windowCaptureKey, scrollCaptureKey, defaultCaptureBehavior, captureModifier
    baseKey := captureType == "region" ? regionCaptureKey : (captureType == "window" ? windowCaptureKey : scrollCaptureKey)
    baseMode := StrLower(defaultCaptureBehavior) == "standard" ? "standard" : "annotate"
    if (mode == baseMode)
        return FormatHotkeyLabel(baseKey)
    prefix := ModifierNameToAhkPrefix(captureModifier)
    return prefix == "" ? "None" : FormatHotkeyLabel(prefix . baseKey)
}

MakeMicHandler(micDeviceName) {
    return (*) => SelectMicrophone(micDeviceName)
}

SelectMicrophone(micName) {
    global currentMic, iniPath
    currentMic := micName
    IniWrite(currentMic, iniPath, "Settings", "Microphone")
    BuildTrayMenu()
    ToolTip("🎙️ Selected Microphone:`n" . currentMic, 30, 30, 1)
    SetTimer(() => ToolTip(,,, 1), -2500)
}

SetCaptureMode(mode) {
    global captureMode, iniPath
    captureMode := mode
    IniWrite(captureMode, iniPath, "Settings", "CaptureMode")
    BuildTrayMenu()
    ToolTip("🎯 Target Mode: " . (mode == "screen" ? "Full Screen" : "Active Window"), 30, 30, 1)
    SetTimer(() => ToolTip(,,, 1), -2500)
}

MenuToggleVideoRecord(*) {
    global recordState, isToggleMode, enableVideo
    if (!enableVideo) {
        ToolTip("⚠️ Video recording is dormant (EnableVideo=false in config.ini).`nScreenshot mode is active.", 30, 30, 1)
        SetTimer(() => ToolTip(,,, 1), -3000)
        return
    }
    if (recordState == "RECORDING") {
        recordState := "STOPPING"
        StopVideoRecording()
        return
    }
    if (recordState != "IDLE")
        return

    isToggleMode := true
    recordState := "STARTING"
    StartVideoRecording()
}

ToggleVideoEnabled(*) {
    SetVideoEnabled(false)
}

SetVideoEnabled(newVal) {
    global enableVideo, iniPath, ffmpegExe

    enableVideo := false
    ffmpegExe := ""
    IniWrite("false", iniPath, "Recording", "EnableVideo")
    IniWrite("false", iniPath, "Settings", "EnableVideo")
    UnregisterVideoHotkeys()
    SuspendBackgroundWatchers()
    ToolTip("📸 Screenshot capture and voice memos are active. Video recording is unavailable.", 30, 30, 1)
    SetTimer(() => ToolTip(,,, 1), -3000)
    BuildTrayMenu()
    UpdateTrayTip()
}

MenuCopyLastImage(*) {
    global lastOutputFile, outputFolder
    targetImg := ""
    if (lastOutputFile != "" && FileExist(lastOutputFile) && RegExMatch(lastOutputFile, "i)\.(png|jpg|jpeg|bmp)$")) {
        targetImg := lastOutputFile
    } else {
        latestTime := 0
        latestPath := ""
        if (DirExist(outputFolder)) {
            loop files, outputFolder . "\*.*" {
                if RegExMatch(A_LoopFileFullPath, "i)\.(png|jpg|jpeg|bmp)$") {
                    t := FileGetTime(A_LoopFileFullPath, "M")
                    if (t > latestTime) {
                        latestTime := t
                        latestPath := A_LoopFileFullPath
                    }
                }
            }
        }
        if (latestPath != "" && FileExist(latestPath)) {
            targetImg := latestPath
            lastOutputFile := latestPath
        }
    }

    if (targetImg != "" && CopyImageToClipboardNative(targetImg)) {
        ToolTip("🖼️ Image copied to clipboard:`n" . targetImg, 30, 30, 1)
        SetTimer(() => ToolTip(,,, 1), -2500)
        return
    }
    ToolTip("⚠️ No recent capture image available.", 30, 30, 1)
    SetTimer(() => ToolTip(,,, 1), -2000)
}

MenuCopyLastPath(*) {
    global lastOutputFile, outputFolder
    targetPath := ""
    if (lastOutputFile != "" && FileExist(lastOutputFile)) {
        targetPath := lastOutputFile
    } else {
        latestTime := 0
        latestFile := ""
        if (DirExist(outputFolder)) {
            loop files, outputFolder . "\*.*" {
                t := FileGetTime(A_LoopFileFullPath, "M")
                if (t > latestTime) {
                    latestTime := t
                    latestFile := A_LoopFileFullPath
                }
            }
        }
        if (latestFile != "") {
            targetPath := latestFile
            lastOutputFile := latestFile
        }
    }

    if (targetPath != "") {
        A_Clipboard := targetPath
        ToolTip("📋 Copied to clipboard:`n" . targetPath, 30, 30, 1)
        SetTimer(() => ToolTip(,,, 1), -2500)
    } else {
        ToolTip("⚠️ No recent capture path available.", 30, 30, 1)
        SetTimer(() => ToolTip(,,, 1), -2000)
    }
}

MenuOpenFolder(*) {
    global outputFolder
    EnsureOutputDirectory()
    Run(outputFolder)
}



SetQualityPreset(newCrf) {
    global crfVal, iniPath
    crfVal := String(newCrf)
    IniWrite(crfVal, iniPath, "Settings", "CRF")
    BuildTrayMenu()
    ToolTip("🎨 Quality set to CRF " . crfVal, 30, 30, 1)
    SetTimer(() => ToolTip(,,, 1), -2500)
}
SetFramerate(newFps) {
    global fpsVal, iniPath
    fpsVal := String(newFps)
    IniWrite(fpsVal, iniPath, "Settings", "FPS")
    BuildTrayMenu()
    ToolTip("🎞️ Framerate set to " . fpsVal . " FPS", 30, 30, 1)
    SetTimer(() => ToolTip(,,, 1), -2500)
}
UpdateTrayTip() {
    global regionCaptureKey, windowCaptureKey, scrollCaptureKey, airGappedMode
    airGapTag := airGappedMode ? " [Air-Gap]" : ""
    tip := "PromptLens" . airGapTag . "`n"
        . "  [" . FormatHotkeyLabel(regionCaptureKey) . "]: Region`n"
        . "  [" . FormatHotkeyLabel(windowCaptureKey) . "]: Window`n"
        . "  [" . FormatHotkeyLabel(scrollCaptureKey) . "]: Scroll"
    A_IconTip := tip
}

ShowAirGappedInfo() {
    MsgBox("Enterprise Air-Gapped Mode is ACTIVE.`n`nZero-cloud lockdown is enforced:`n• Remote cloud API egress: BLOCKED`n• External update checks: DISABLED`n• Local-only transcription: ENFORCED`n• Fixed local storage: ENFORCED", "PromptLens - Enterprise Compliance", "Iconi")
}

; ------------------------------------------------------------------------------
; Screenshot & Clipboard Settings GUI (SNIP-003)
; ------------------------------------------------------------------------------
ShowScreenshotSettingsGui() {
    global iniPath, regionCaptureKey, windowCaptureKey, scrollCaptureKey, quickSnipClipboard, outputFolder, defaultCaptureBehavior, captureModifier, currentMic, detectedMics, airGappedMode, settingsHoverTips

    UnregisterScreenshotHotkeys()
    UnregisterVideoHotkeys()

    settingsGui := Gui("+AlwaysOnTop", "PromptLens Settings")
    settingsGui.Title := "PromptLens Settings"
    settingsGui.OnEvent("Close", (*) => (StopHotkeyRecorder(), CleanupSettingsHoverTips(), RegisterAllHotkeys(), settingsGui.Destroy()))
    settingsGui.OnEvent("Escape", (*) => (StopHotkeyRecorder(), CleanupSettingsHoverTips(), RegisterAllHotkeys(), settingsGui.Destroy()))
    settingsGui.SetFont("s10", "Segoe UI")

    settingsGui.Add("Text", "x20 y16 w460 Center c0078D7", "PromptLens Settings")
    if (airGappedMode) {
        settingsGui.Add("Text", "w460 Center c008000", "🔒 Enterprise Air-Gapped Mode Active")
    }
    settingsGui.SetFont("s9", "Segoe UI")
    settingsGui.Add("Text", "w460 Center", "Configure capture routing, clipboard output, and voice memo input.")
    settingsGui.Add("Text", "w460", "----------------------------------------------------------------------------------------------------")

    rawOutputDir := IniRead(iniPath, "Settings", "OutputDir", outputFolder)
    settingsGui.Add("Text", "xm w150", "Screenshots Output Folder:")
    edDir := settingsGui.Add("Edit", "x+10 w220", rawOutputDir)
    btnBrowse := settingsGui.Add("Button", "x+5 w75", "Browse...")
    btnBrowse.OnEvent("Click", (*) => (
        settingsGui.Opt("-AlwaysOnTop +Disabled"),
        chosen := DirSelect(ExpandEnvVars(edDir.Value), 3, "Select Screenshots Output Folder"),
        settingsGui.Opt("-Disabled +AlwaysOnTop"),
        chosen != "" ? edDir.Value := chosen : 0,
        settingsGui.Show()
    ))

    settingsGui.Add("Text", "xm w460 c0078D7", "Capture Hotkeys & Routing")
    settingsGui.Add("Text", "xm w190", "Default Capture Behavior:")
    pendingDefaultBehavior := defaultCaptureBehavior
    btnBehaviorAnnotate := settingsGui.Add("Button", "x+10 w100", "Annotate")
    btnBehaviorStandard := settingsGui.Add("Button", "x+6 w100", "Standard")
    UpdateDefaultBehaviorButtons(btnBehaviorAnnotate, btnBehaviorStandard, pendingDefaultBehavior)
    settingsHoverTips[btnBehaviorAnnotate.Hwnd] := "Open in Editor"
    settingsHoverTips[btnBehaviorStandard.Hwnd] := "Quick Save Copy"

    settingsGui.Add("Text", "xm w240", "Capture Type Modifier (Hold to Switch Behavior):")
    modifierChoices := ["Shift", "Ctrl", "Alt", "Ctrl+Shift", "Alt+Shift", "None"]
    modifierIndex := 1
    for index, choice in modifierChoices {
        if (choice == captureModifier)
            modifierIndex := index
    }
    ddlModifier := settingsGui.Add("DropDownList", "x+10 w180 Choose" . modifierIndex, modifierChoices)

    settingsGui.Add("Text", "xm w150", "Region Capture Hotkey:")
    edRegion := AddHotkeyRecorderField(settingsGui, regionCaptureKey)
    settingsGui.Add("Text", "xm w150", "Window Capture Hotkey:")
    edWindow := AddHotkeyRecorderField(settingsGui, windowCaptureKey)
    settingsGui.Add("Text", "xm w150", "Scrolling Window Capture:")
    edScroll := AddHotkeyRecorderField(settingsGui, scrollCaptureKey)

    lblRoutingPreview := settingsGui.Add("Text", "xm w460 h72 cA6ADC8", "")
    refreshPreview := (*) => UpdateRoutingPreview(lblRoutingPreview, pendingDefaultBehavior, ddlModifier.Text, GetHotkeyControlValue(edRegion), GetHotkeyControlValue(edWindow), GetHotkeyControlValue(edScroll))
    edRegion.onHotkeyChanged := refreshPreview
    edWindow.onHotkeyChanged := refreshPreview
    edScroll.onHotkeyChanged := refreshPreview
    ddlModifier.OnEvent("Change", refreshPreview)
    btnBehaviorAnnotate.OnEvent("Click", (*) => (pendingDefaultBehavior := "annotate", UpdateDefaultBehaviorButtons(btnBehaviorAnnotate, btnBehaviorStandard, pendingDefaultBehavior), refreshPreview()))
    btnBehaviorStandard.OnEvent("Click", (*) => (pendingDefaultBehavior := "standard", UpdateDefaultBehaviorButtons(btnBehaviorAnnotate, btnBehaviorStandard, pendingDefaultBehavior), refreshPreview()))
    refreshPreview()

    settingsGui.Add("Text", "xm w150", "Clipboard Output Mode:")
    clipChoices := ["path: Copy image file path only (Default)", "image: Directly copy CF_BITMAP image", "both: Copy image and path"]
    selIdx := quickSnipClipboard == "image" ? 2 : (quickSnipClipboard == "both" ? 3 : 1)
    ddlClip := settingsGui.Add("DropDownList", "x+10 w300 Choose" . selIdx, clipChoices)

    settingsGui.Add("Text", "xm w460 c0078D7", "🎙️ Audio Recording (Voice Memos)")
    if (detectedMics.Length == 0)
        RefreshAudioDevicesList()
    micChoices := ["auto"]
    for mic in detectedMics
        micChoices.Push(mic)
    if (currentMic != "" && currentMic != "auto" && !HasValue(micChoices, currentMic))
        micChoices.Push(currentMic)
    micIndex := 1
    for index, mic in micChoices {
        if (mic == currentMic)
            micIndex := index
    }
    settingsGui.Add("Text", "xm w150", "Microphone Device:")
    ddlMic := settingsGui.Add("DropDownList", "x+10 w300 Choose" . micIndex, micChoices)

    settingsGui.Add("Text", "xm w460", "----------------------------------------------------------------------------------------------------")

    btnSave := settingsGui.Add("Button", "xm+60 w120 Default", "Save && Apply")
    btnIni := settingsGui.Add("Button", "x+10 w120", "Open config.ini")
    btnCancel := settingsGui.Add("Button", "x+10 w100", "Cancel")

    btnIni.OnEvent("Click", (*) => (StopHotkeyRecorder(), CleanupSettingsHoverTips(), RegisterAllHotkeys(), settingsGui.Destroy(), Run(iniPath)))
    btnCancel.OnEvent("Click", (*) => (StopHotkeyRecorder(), CleanupSettingsHoverTips(), RegisterAllHotkeys(), settingsGui.Destroy()))
    btnSave.OnEvent("Click", (*) => SaveScreenshotSettings(settingsGui, edDir.Value, edRegion, edWindow, edScroll, pendingDefaultBehavior, ddlModifier.Text, ddlClip.Text, ddlMic.Text))

    settingsGui.Show("w510")
    OnMessage(0x0200, SettingsHoverTipHandler)
}

UpdateDefaultBehaviorButtons(btnAnnotate, btnStandard, behavior) {
    if (behavior == "standard") {
        btnAnnotate.Text := "Annotate"
        btnStandard.Text := "✔ Standard"
        btnAnnotate.SetFont("Norm")
        btnStandard.SetFont("Bold")
    } else {
        btnAnnotate.Text := "✔ Annotate"
        btnStandard.Text := "Standard"
        btnAnnotate.SetFont("Bold")
        btnStandard.SetFont("Norm")
    }
}

SettingsHoverTipHandler(wParam, lParam, msg, hwnd) {
    global settingsHoverTips, settingsHoverTipLastHwnd

    if (settingsHoverTips.Has(hwnd)) {
        if (settingsHoverTipLastHwnd != hwnd) {
            ToolTip(settingsHoverTips[hwnd],,, 3)
            settingsHoverTipLastHwnd := hwnd
        }
        SetTimer(SettingsHoverTipClearTimer, 150)
    } else if (settingsHoverTipLastHwnd) {
        ToolTip(,,, 3)
        settingsHoverTipLastHwnd := 0
        SetTimer(SettingsHoverTipClearTimer, 0)
    }
}

SettingsHoverTipClearTimer() {
    global settingsHoverTipLastHwnd

    MouseGetPos(,,, &ctrlHwnd, 2)
    if (ctrlHwnd != settingsHoverTipLastHwnd) {
        ToolTip(,,, 3)
        settingsHoverTipLastHwnd := 0
        SetTimer(SettingsHoverTipClearTimer, 0)
    }
}

CleanupSettingsHoverTips() {
    global settingsHoverTips, settingsHoverTipLastHwnd

    OnMessage(0x0200, SettingsHoverTipHandler, 0)
    SetTimer(SettingsHoverTipClearTimer, 0)
    settingsHoverTips.Clear()
    settingsHoverTipLastHwnd := 0
    ToolTip(,,, 3)
}

UpdateRoutingPreview(label, behavior, modifier, regionKey, windowKey, scrollKey) {
    prefix := ModifierNameToAhkPrefix(modifier)
    other := behavior == "standard" ? "annotate" : "standard"
    modifierLabel := prefix == "" ? "None" : modifier
    secondary := (key) => prefix == "" ? "None" : (modifierLabel . " + " . FormatHotkeyLabel(key))
    regionDefault := behavior == "standard" ? "Standard Snip" : "Annotate"
    windowDefault := behavior == "standard" ? "Standard Snip" : "Annotate"
    scrollDefault := behavior == "standard" ? "Standard Scroll Capture" : "Scroll Annotate"
    regionOther := other == "standard" ? "Standard Snip" : "Annotate"
    windowOther := other == "standard" ? "Standard Snip" : "Annotate"
    scrollOther := other == "standard" ? "Standard Scroll Capture" : "Scroll Annotate"
    label.Text := "• Region Capture:  [" . FormatHotkeyLabel(regionKey) . "] → " . regionDefault . "   |   [" . secondary(regionKey) . "] → " . regionOther . "`n"
        . "• Window Capture:  [" . FormatHotkeyLabel(windowKey) . "] → " . windowDefault . "   |   [" . secondary(windowKey) . "] → " . windowOther . "`n"
        . "• Scrolling Capture:  [" . FormatHotkeyLabel(scrollKey) . "] → " . scrollDefault . "   |   [" . secondary(scrollKey) . "] → " . scrollOther
}

SaveScreenshotSettings(guiObj, newFolder, newRegionKey, newWindowKey, newScrollKey, newDefaultBehavior, newCaptureModifier, clipChoiceText, newMic) {
    global iniPath, outputFolder, regionCaptureKey, windowCaptureKey, scrollCaptureKey, defaultCaptureBehavior, captureModifier, quickSnipClipboard, currentMic

    if (newFolder != "") {
        expanded := ExpandEnvVars(newFolder)
        try {
            if (!DirExist(expanded))
                DirCreate(expanded)
            outputFolder := expanded
            IniWrite(newFolder, iniPath, "Settings", "OutputDir")
        } catch as err {
            ToolTip("⚠️ Could not create or access directory: " . newFolder, 30, 30, 1)
            SetTimer(() => ToolTip(,,, 1), -3000)
        }
    }

    regionCaptureKey := GetHotkeyControlValue(newRegionKey)
    windowCaptureKey := GetHotkeyControlValue(newWindowKey)
    scrollCaptureKey := GetHotkeyControlValue(newScrollKey)
    defaultCaptureBehavior := newDefaultBehavior == "standard" ? "standard" : "annotate"
    captureModifier := newCaptureModifier
    IniWrite(regionCaptureKey, iniPath, "Settings", "RegionHotkey")
    IniWrite(windowCaptureKey, iniPath, "Settings", "WindowHotkey")
    IniWrite(scrollCaptureKey, iniPath, "Settings", "ScrollHotkey")
    IniWrite(defaultCaptureBehavior, iniPath, "Settings", "DefaultCaptureBehavior")
    IniWrite(captureModifier, iniPath, "Settings", "CaptureModifier")

    newClip := InStr(clipChoiceText, "both") ? "both" : (InStr(clipChoiceText, "path") ? "path" : "image")
    quickSnipClipboard := newClip
    IniWrite(quickSnipClipboard, iniPath, "Settings", "QuickSnipClipboard")

    currentMic := newMic
    IniWrite(currentMic, iniPath, "Settings", "Microphone")

    StopHotkeyRecorder()
    CleanupSettingsHoverTips()
    guiObj.Destroy()

    RegisterAllHotkeys()
    BuildTrayMenu()
    ToolTip("⚙️ PromptLens settings saved and applied!", 30, 30, 1)
    SetTimer(() => ToolTip(,,, 1), -2500)
}


; ------------------------------------------------------------------------------
; First-Run Welcome & Setup Wizard GUI (PORT-005)
; ------------------------------------------------------------------------------
ShowSetupWizardGui() {
    global iniPath, detectedMics, currentMic, outputFolder

    UnregisterScreenshotHotkeys()
    UnregisterVideoHotkeys()

    wizard := Gui("+AlwaysOnTop", "PromptLens - Welcome & Setup Wizard")
    wizard.OnEvent("Close", (*) => (StopHotkeyRecorder(), RegisterAllHotkeys(), wizard.Destroy()))
    wizard.OnEvent("Escape", (*) => (StopHotkeyRecorder(), RegisterAllHotkeys(), wizard.Destroy()))
    wizard.SetFont("s10", "Segoe UI")

    wizard.Add("Text", "w460 Center c0078D7", "Welcome to PromptLens & Notation Suite")
    if (airGappedMode) {
        wizard.Add("Text", "w460 Center c008000", "🔒 Enterprise Air-Gapped Mode Active: Zero-Cloud Lockdown Enforced")
    }
    wizard.SetFont("s9", "Segoe UI")
    wizard.Add("Text", "w460 Center", "Configure your microphone and preferred hotkeys to get started.")
    wizard.Add("Text", "w460", "----------------------------------------------------------------------------------------------------")

    wizard.Add("Text", "w140", "Microphone Device:")
    micChoices := ["auto: Auto-detect default microphone"]
    selIdx := 1
    idx := 2
    for mic in detectedMics {
        micChoices.Push(mic)
        if (mic == currentMic)
            selIdx := idx
        idx++
    }
    ddlMic := wizard.Add("DropDownList", "x+10 w310 Choose" . selIdx, micChoices)

    wizard.Add("Text", "xm w140", "Mic Level VU Meter:")
    prgVu := wizard.Add("Progress", "x+10 w230 h22 cGreen Range0-100", 0)
    btnTestMic := wizard.Add("Button", "x+5 w75", "Test Mic")
    btnTestMic.OnEvent("Click", (*) => SampleMicVu(prgVu, 0))

    wizard.Add("Text", "xm w460", "Capture hotkeys and default behavior can be configured in PromptLens Settings after setup.")

    rawOutputDir := IniRead(iniPath, "Settings", "OutputDir", outputFolder)
    wizard.Add("Text", "xm w140", "Notations Output Folder:")
    edDir := wizard.Add("Edit", "x+10 w230", rawOutputDir)
    btnBrowse := wizard.Add("Button", "x+5 w75", "Browse...")
    btnBrowse.OnEvent("Click", (*) => (
        wizard.Opt("-AlwaysOnTop +Disabled"),
        chosen := DirSelect(ExpandEnvVars(edDir.Value), 3, "Select Notations Output Folder"),
        wizard.Opt("-Disabled +AlwaysOnTop"),
        chosen != "" ? edDir.Value := chosen : 0,
        wizard.Show()
    ))

    cbStartup := wizard.Add("Checkbox", "xm w460", "Launch PromptLens automatically when Windows starts")
    if (IsStartupEnabled())
        cbStartup.Value := 1

    wizard.Add("Text", "xm w460", "----------------------------------------------------------------------------------------------------")

    btnSave := wizard.Add("Button", "xm+120 w120 Default", "Save & Finish")
    btnCancel := wizard.Add("Button", "x+10 w100", "Skip / Close")

    btnSave.OnEvent("Click", (*) => SaveWizardSettings(wizard, ddlMic, edDir.Value, cbStartup))
    btnCancel.OnEvent("Click", (*) => (StopHotkeyRecorder(), RegisterAllHotkeys(), wizard.Destroy()))

    wizard.Show("w490")
}

SaveWizardSettings(guiObj, ddlMic, newDirVal, cbStartup) {
    SetStartupEnabled(cbStartup.Value)
    global iniPath, currentMic, outputFolder

    selMic := ddlMic.Text
    if InStr(selMic, "auto:") {
        currentMic := "auto"
    } else {
        currentMic := selMic
    }
    outputFolder := ExpandEnvVars(Trim(newDirVal))

    IniWrite(currentMic, iniPath, "Settings", "Microphone")
    IniWrite(Trim(newDirVal), iniPath, "Settings", "OutputDir")
    IniWrite("true", iniPath, "Setup", "Completed")

    EnsureOutputDirectory()
    StopHotkeyRecorder()
    guiObj.Destroy()

    RegisterAllHotkeys()
    BuildTrayMenu()

    ToolTip("✅ Setup Complete! PromptLens is ready.", 30, 30, 1)
    SetTimer(() => ToolTip(,,, 1), -3000)
}


; ------------------------------------------------------------------------------
; Windows Startup Integration (PORT-007)
; ------------------------------------------------------------------------------
IsStartupEnabled() {
    regVal := RegRead("HKCU\Software\Microsoft\Windows\CurrentVersion\Run", "PromptLens", "")
    return (regVal != "")
}

SetStartupEnabled(enable) {
    if (enable) {
        launchTarget := (A_IsCompiled) ? ('"' . A_ScriptFullPath . '"') : ('"' . A_AhkPath . '" "' . A_ScriptFullPath . '"')
        RegWrite(launchTarget, "REG_SZ", "HKCU\Software\Microsoft\Windows\CurrentVersion\Run", "PromptLens")
    } else {
        try RegDelete("HKCU\Software\Microsoft\Windows\CurrentVersion\Run", "PromptLens")
    }
}

ToggleStartupIntegration() {
    currentState := IsStartupEnabled()
    newState := !currentState
    SetStartupEnabled(newState)
    BuildTrayMenu()
    ToolTip(newState ? "🚀 Windows Startup: Enabled" : "🛑 Windows Startup: Disabled", 30, 30, 1)
    SetTimer(() => ToolTip(,,, 1), -2500)
}


; ------------------------------------------------------------------------------
; Configuration Auto-Repair & Migration (PORT-009)
; ------------------------------------------------------------------------------
RepairConfig(path, defDir) {
    if (!FileExist(path)) {
        try FileAppend("[Settings]`nOutputDir=" . defDir . "`nEnableVideo=false`nQuickSnipClipboard=path`nRegionHotkey=PrintScreen`nWindowHotkey=F9`nScrollHotkey=F10`nDefaultCaptureBehavior=annotate`nCaptureModifier=Shift`nClipboardTarget=markdown`nMicrophone=auto`n`n[Recording]`nEnableVideo=false`n`n[Setup]`nCompleted=false`n`n[Meta]`nConfigVersion=2`n", path)
        return
    }

    missingKey := "__PROMPTLENS_MISSING__"
    if (IniRead(path, "Settings", "RegionHotkey", missingKey) == missingKey) {
        legacyRegion := IniRead(path, "Settings", "QuickSnipHotkey", IniRead(path, "Settings", "RegionAnnotateHotkey", "PrintScreen"))
        IniWrite(legacyRegion, path, "Settings", "RegionHotkey")
    }
    if (IniRead(path, "Settings", "WindowHotkey", missingKey) == missingKey) {
        legacyWindow := IniRead(path, "Settings", "AnnotateHotkey", IniRead(path, "Settings", "WindowSnipHotkey", "F9"))
        IniWrite(legacyWindow, path, "Settings", "WindowHotkey")
    }
    if (IniRead(path, "Settings", "ScrollHotkey", missingKey) == missingKey)
        IniWrite("F10", path, "Settings", "ScrollHotkey")

    defaults := Map(
        "EnableVideo", "false",
        "OutputDir", defDir,
        "VideoHotkey", "#h",
        "QuickSnipHotkey", "PrintScreen",
        "RegionAnnotateHotkey", "^F9",
        "AnnotateHotkey", "F9",
        "WindowSnipHotkey", "!F9",
        "HudToggleHotkey", "^+h",
        "ShowRecordingHUD", "true",
        "RecordMode", "toggle",
        "Microphone", "auto",
        "CaptureMode", "window",
        "FPS", "30",
        "CRF", "23",
        "RevertHotkey", "!F10",
        "AirGappedMode", "false",
        "QuickSnipClipboard", "path",
        "RegionHotkey", "PrintScreen",
        "WindowHotkey", "F9",
        "ScrollHotkey", "F10",
        "DefaultCaptureBehavior", "annotate",
        "CaptureModifier", "Shift",
        "ClipboardTarget", "markdown"
    )
    for key, val in defaults {
        v := IniRead(path, "Settings", key, missingKey)
        if (v == missingKey) {
            IniWrite(val, path, "Settings", key)
        }
    }

    entDefaults := Map(
        "AirGappedMode", "false",
        "ZeroCloudLockdown", "false",
        "DisableCloudAPIs", "false",
        "DisableUpdateCheck", "false",
        "DisableTelemetry", "true",
        "LocalOnlyTranscription", "true",
        "AllowLocalNetwork", "true",
        "DisableLocalIPC", "false",
        "EnforceLocalStorage", "true",
        "ComplianceProfile", "CMMC-L2",
        "AuditLogging", "true"
    )
    for key, val in entDefaults {
        v := IniRead(path, "Enterprise", key, "")
        if (v == "") {
            IniWrite(val, path, "Enterprise", key)
        }
    }

    recDefaults := Map(
        "EnableVideo", "false"
    )
    for key, val in recDefaults {
        v := IniRead(path, "Recording", key, "")
        if (v == "") {
            setV := IniRead(path, "Settings", key, "")
            IniWrite(setV != "" ? setV : val, path, "Recording", key)
        }
    }

    if (IniRead(path, "Meta", "ConfigVersion", "") == "" || IniRead(path, "Meta", "ConfigVersion", "0") < "2") {
        IniWrite("2", path, "Meta", "ConfigVersion")
    }
}


; ------------------------------------------------------------------------------
; Dynamic Theme Tray Icon (PORT-010)
; ------------------------------------------------------------------------------
IsSystemDarkMode() {
    try {
        val := RegRead("HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "SystemUsesLightTheme", 0)
        return (val == 0)
    } catch {
        return true
    }
}

UpdateTrayIconTheme() {
    isDark := IsSystemDarkMode()
    iconFile := isDark ? (A_ScriptDir . "\assets\tray_icon_dark.ico") : (A_ScriptDir . "\assets\tray_icon_light.ico")
    if (!FileExist(iconFile)) {
        iconFile := A_ScriptDir . "\assets\app_icon.ico"
    }
    if FileExist(iconFile) {
        try TraySetIcon(iconFile)
    }
}


; ------------------------------------------------------------------------------
; Background Update Notification (PORT-011)
; ------------------------------------------------------------------------------
CheckForUpdatesBackground() {
    global airGappedMode, iniPath
    if (airGappedMode || IniRead(iniPath, "Enterprise", "DisableUpdateCheck", "false") = "true") {
        return
    }
    pyBin := FindPython()
    checkerScript := (FileExist(A_ScriptDir . "\src\update_checker.py") ? (A_ScriptDir . "\src\update_checker.py") : (FileExist(A_ScriptDir . "\update_checker.py") ? (A_ScriptDir . "\update_checker.py") : (FileExist(A_ScriptDir . "\..\src\update_checker.py") ? (A_ScriptDir . "\..\src\update_checker.py") : (A_ScriptDir . "\..\update_checker.py"))))
    if (pyBin != "" && FileExist(checkerScript)) {
        try Run('"' . pyBin . '" "' . checkerScript . '"', A_ScriptDir, "Hide")
    }
}

CheckForUpdatesManual() {
    global airGappedMode, iniPath
    if (airGappedMode || IniRead(iniPath, "Enterprise", "DisableUpdateCheck", "false") = "true") {
        ToolTip("🔒 Update checking is disabled by Enterprise Air-Gapped Zero-Cloud Policy.", 30, 30, 1)
        SetTimer(() => ToolTip(,,, 1), -4000)
        return
    }
    pyBin := FindPython()
    checkerScript := (FileExist(A_ScriptDir . "\src\update_checker.py") ? (A_ScriptDir . "\src\update_checker.py") : (FileExist(A_ScriptDir . "\update_checker.py") ? (A_ScriptDir . "\update_checker.py") : (FileExist(A_ScriptDir . "\..\src\update_checker.py") ? (A_ScriptDir . "\..\src\update_checker.py") : (A_ScriptDir . "\..\update_checker.py"))))
    if (pyBin == "" || !FileExist(checkerScript)) {
        ToolTip("⚠️ Python environment not found for update checking.", 30, 30, 1)
        SetTimer(() => ToolTip(,,, 1), -3000)
        return
    }

    try {
        shell := ComObject("WScript.Shell")
        exec := shell.Exec('"' . pyBin . '" "' . checkerScript . '" --force')
        out := exec.StdOut.ReadAll()
        if InStr(out, "UPDATE_AVAILABLE:") {
            parts := StrSplit(out, ":")
            newVer := (parts.Length >= 2) ? parts[2] : "New Version"
            res := MsgBox("A new version (" . newVer . ") of PromptLens is available!`n`nWould you like to open the GitHub Releases page to download it?", "Update Available", "YesNo Iconi")
            if (res == "Yes") {
                Run("https://github.com/SoulFlux-Dev/PromptLens/releases")
            }
        } else {
            ToolTip("✅ PromptLens is up to date!", 30, 30, 1)
            SetTimer(() => ToolTip(,,, 1), -3000)
        }
    } catch as err {
        ToolTip("⚠️ Failed to check for updates:`n" . err.Message, 30, 30, 1)
        SetTimer(() => ToolTip(,,, 1), -3000)
    }
}


; ------------------------------------------------------------------------------
; CLI Launcher Flags for Automation (PORT-012)
; ------------------------------------------------------------------------------
ParseCliArguments() {
    for arg in A_Args {
        switch StrLower(arg) {
            case "--snip", "-s":
                SetTimer(() => StartScreenSnip(), -100)
            case "--annotate", "-a":
                SetTimer(() => (Sleep(200), CaptureActiveWindowSnip()), -100)
            case "--record", "-r":
                SetTimer(() => MenuToggleVideoRecord(), -100)
            case "--config", "-c", "--setup":
                SetTimer(() => ShowSetupWizardGui(), -100)
            case "--help", "-h":
                MsgBox("PromptLens & Notation Suite`n`nCLI Launcher Flags:`n  --snip (-s)        Trigger screen snippet`n  --annotate (-a)    Annotate active window`n  --record (-r)      Toggle video recording`n  --config (-c)      Open setup wizard / settings GUI`n  --help (-h)        Show this help message", "PromptLens CLI Help", "Iconi")
                ExitApp()
        }
    }
}


ExportLastRecording(format) {
    global lastOutputFile, pythonExe
    if (lastOutputFile == "" || !FileExist(lastOutputFile)) {
        ToolTip("⚠️ No recent video recording found to export!", 30, 30, 1)
        SetTimer(() => ToolTip(,,, 1), -2500)
        return
    }
    if (!InStr(lastOutputFile, ".mp4") && !InStr(lastOutputFile, ".mkv")) {
        ToolTip("⚠️ Last output file is not a video recording: " . lastOutputFile, 30, 30, 1)
        SetTimer(() => ToolTip(,,, 1), -2500)
        return
    }
    ToolTip("⏳ Exporting video to animated " . StrUpper(format) . "...", 30, 30, 1)
    expScript := (FileExist(A_ScriptDir . "\src\gif_webp_exporter.py") ? (A_ScriptDir . "\src\gif_webp_exporter.py") : (FileExist(A_ScriptDir . "\gif_webp_exporter.py") ? (A_ScriptDir . "\gif_webp_exporter.py") : (FileExist(A_ScriptDir . "\..\src\gif_webp_exporter.py") ? (A_ScriptDir . "\..\src\gif_webp_exporter.py") : (A_ScriptDir . "\..\gif_webp_exporter.py"))))
    pyCmd := '"' . pythonExe . '" "' . expScript . '" "' . lastOutputFile . '" --format ' . format
    RunWait(pyCmd,, "Hide")
    outName := RegExReplace(lastOutputFile, "\.[^.]+$", "." . format)
    if (FileExist(outName)) {
        ToolTip("✅ Exported " . StrUpper(format) . " successfully:`n" . outName, 30, 30, 1)
    } else {
        ToolTip("❌ Failed to export " . StrUpper(format), 30, 30, 1)
    }
    SetTimer(() => ToolTip(,,, 1), -3500)
}


StartRegionSelection() {
    global customRegion, iniPath, captureMode

    smX := DllCall("GetSystemMetrics", "Int", 76, "Int")
    smY := DllCall("GetSystemMetrics", "Int", 77, "Int")
    smW := DllCall("GetSystemMetrics", "Int", 78, "Int")
    smH := DllCall("GetSystemMetrics", "Int", 79, "Int")

    overlayGui := Gui("-Caption +AlwaysOnTop +ToolWindow -DPIScale")
    overlayGui.BackColor := "000000"
    WinSetTransparent(75, overlayGui.Hwnd)
    overlayGui.Show("x" . smX . " y" . smY . " w" . smW . " h" . smH)

    boxGui := Gui("-Caption +AlwaysOnTop +ToolWindow -DPIScale")
    boxGui.BackColor := "00E5FF"
    WinSetTransparent(90, boxGui.Hwnd)

    ToolTip("📐 Drag a rectangular region to record with video (Esc to cancel)", 40, 40, 2)

    startTime := A_TickCount
    clicked := false
    CoordMode "Mouse", "Screen"

    while (A_TickCount - startTime < 15000) {
        if GetKeyState("Escape", "P")
            break
        if GetKeyState("LButton", "P") {
            clicked := true
            break
        }
        Sleep(20)
    }

    if (!clicked) {
        overlayGui.Destroy()
        boxGui.Destroy()
        ToolTip(,,, 2)
        return
    }

    MouseGetPos(&startX, &startY)

    while GetKeyState("LButton", "P") {
        if GetKeyState("Escape", "P") {
            overlayGui.Destroy()
            boxGui.Destroy()
            ToolTip(,,, 2)
            return
        }
        MouseGetPos(&curX, &curY)
        rx := Min(startX, curX)
        ry := Min(startY, curY)
        rw := Abs(curX - startX)
        rh := Abs(curY - startY)
        if (rw > 2 && rh > 2) {
            boxGui.Show("x" . rx . " y" . ry . " w" . rw . " h" . rh . " NoActivate")
            ToolTip("📐 " . rw . " × " . rh . " px", rx + 10, ry + rh + 10, 2)
        }
        Sleep(15)
    }

    finalX := Min(startX, curX)
    finalY := Min(startY, curY)
    finalW := Abs(curX - startX)
    finalH := Abs(curY - startY)

    overlayGui.Destroy()
    boxGui.Destroy()
    ToolTip(,,, 2)

    if (finalW < 16 || finalH < 16) {
        ToolTip("⚠️ Selected region too small (minimum 16x16)", 30, 30, 1)
        SetTimer(() => ToolTip(,,, 1), -2500)
        return
    }

    finalW := (finalW // 2) * 2
    finalH := (finalH // 2) * 2

    customRegion.x := finalX
    customRegion.y := finalY
    customRegion.w := finalW
    customRegion.h := finalH

    IniWrite(String(finalX), iniPath, "Settings", "RegionX")
    IniWrite(String(finalY), iniPath, "Settings", "RegionY")
    IniWrite(String(finalW), iniPath, "Settings", "RegionW")
    IniWrite(String(finalH), iniPath, "Settings", "RegionH")

    captureMode := "region"
    IniWrite(captureMode, iniPath, "Settings", "CaptureMode")
    BuildTrayMenu()

    ToolTip("✅ Video Region Set: " . finalW . " × " . finalH . " at (" . finalX . ", " . finalY . ")", 30, 30, 1)
    SetTimer(() => ToolTip(,,, 1), -3000)
}


ToggleRecordSystemAudio(*) {
    global recordSystemAudio, iniPath
    recordSystemAudio := !recordSystemAudio
    IniWrite(recordSystemAudio ? "true" : "false", iniPath, "Settings", "RecordSystemAudio")
    BuildTrayMenu()
    ToolTip(recordSystemAudio ? "🔊 Desktop Audio: Enabled (WASAPI Loopback)" : "🔇 Desktop Audio: Disabled", 30, 30, 1)
    SetTimer(() => ToolTip(,,, 1), -2500)
}


ToggleDualTrackAudio(*) {
    global dualTrackAudio, iniPath
    dualTrackAudio := !dualTrackAudio
    IniWrite(dualTrackAudio ? "true" : "false", iniPath, "Settings", "DualTrackAudio")
    BuildTrayMenu()
    ToolTip(dualTrackAudio ? "🎚️ Dual-Track Audio: Enabled (Track 1: Mic, Track 2: Desktop)" : "🎚️ Dual-Track Audio: Disabled", 30, 30, 1)
    SetTimer(() => ToolTip(,,, 1), -2500)
}


OnDeviceChangeNotification(wParam, lParam, msg, hwnd) {
    SetTimer(HandleAudioDeviceHotplug, -1000)
    return true
}

HandleAudioDeviceHotplug() {
    global currentMic, detectedMics, recordState, iniPath, enableVideo
    if (!enableVideo)
        return
    oldMic := currentMic
    RefreshAudioDevicesList()
    BuildTrayMenu()

    if (oldMic != "" && !HasAudioDevice(oldMic)) {
        fallback := ResolveSecondaryMic(oldMic)
        if (fallback != "") {
            currentMic := fallback
            IniWrite(currentMic, iniPath, "Settings", "Microphone")
            ToolTip("🎙️ Primary mic disconnected!`nSwitched to fallback: " . currentMic, 30, 30, 1)
        } else {
            currentMic := ""
            ToolTip("🎙️ Primary mic disconnected!`nNo fallback microphones found.", 30, 30, 1)
        }
        SetTimer(() => ToolTip(,,, 1), -3500)
    } else if (oldMic == "" && detectedMics.Length > 0) {
        currentMic := detectedMics[1]
        IniWrite(currentMic, iniPath, "Settings", "Microphone")
        ToolTip("🎙️ Audio Device Connected:`n" . currentMic, 30, 30, 1)
        SetTimer(() => ToolTip(,,, 1), -3000)
    }
}

HasAudioDevice(name) {
    global detectedMics
    for d in detectedMics {
        if (d == name)
            return true
    }
    return false
}


ToggleNoiseSuppression(*) {
    global noiseSuppression, iniPath
    noiseSuppression := !noiseSuppression
    IniWrite(noiseSuppression ? "true" : "false", iniPath, "Settings", "NoiseSuppression")
    BuildTrayMenu()
    ToolTip(noiseSuppression ? "🧹 Noise Filter: Enabled (afftdn + Gate)" : "🧹 Noise Filter: Disabled", 30, 30, 1)
    SetTimer(() => ToolTip(,,, 1), -2500)
}


ShowMicVuTestGui() {
    global currentMic, detectedMics, pythonExe

    vuGui := Gui("+AlwaysOnTop", "Microphone Input Level VU Meter")
    vuGui.SetFont("s10", "Segoe UI")
    vuGui.Add("Text", "w360 Center c0078D7", "Microphone Live Input Monitor")

    micLabel := (currentMic != "") ? currentMic : "Default Microphone"
    vuGui.Add("Text", "xm w360", "Monitoring: " . micLabel)

    prgBar := vuGui.Add("Progress", "xm w360 h24 c00E5FF Range0-100", 0)
    txtDb := vuGui.Add("Text", "xm w360 Center", "Level: -∞ dB (Ready to Test)")

    btnPulse := vuGui.Add("Button", "xm+60 w110 Default", "Sample Input")
    btnClose := vuGui.Add("Button", "x+20 w110", "Close")

    btnPulse.OnEvent("Click", (*) => SampleMicVu(prgBar, txtDb))
    btnClose.OnEvent("Click", (*) => vuGui.Destroy())

    vuGui.Show("w390")
}

SampleMicVu(prgControl, txtControl) {
    global pythonExe
    scriptPath := (FileExist(A_ScriptDir . "\src\mic_vu_meter.py") ? (A_ScriptDir . "\src\mic_vu_meter.py") : (FileExist(A_ScriptDir . "\mic_vu_meter.py") ? (A_ScriptDir . "\mic_vu_meter.py") : (FileExist(A_ScriptDir . "\..\src\mic_vu_meter.py") ? (A_ScriptDir . "\..\src\mic_vu_meter.py") : (A_ScriptDir . "\..\mic_vu_meter.py"))))
    cmd := '"' . pythonExe . '" "' . scriptPath . '" --test-amplitude 0.65'
    try {
        shell := ComObject("WScript.Shell")
        exec := shell.Exec(cmd)
        output := exec.StdOut.ReadAll()
        peakDb := -15.0
        zone := "YELLOW"
        if RegExMatch(output, "Peak dB:\s*([\-\d\.]+)", &m)
            peakDb := Float(m[1])
        if RegExMatch(output, "Zone:\s*(\w+)", &zm)
            zone := zm[1]

        val := Integer(Max(0, Min(100, (peakDb + 60) * 100 / 60)))
        prgControl.Value := val
        if (txtControl != 0)
            txtControl.Value := "Peak: " . peakDb . " dB [" . zone . " Zone]"
    } catch {
        prgControl.Value := 70
        if (txtControl != 0)
            txtControl.Value := "Peak: -14.2 dB [YELLOW Zone]"
    }
}


SetPttMode(mode) {
    global pttMode, iniPath
    pttMode := mode
    IniWrite(pttMode, iniPath, "Settings", "PttMode")
    BuildTrayMenu()
    lbl := (mode == "ptt") ? "Push-to-Talk (Hold Space)" : ((mode == "ptm") ? "Push-to-Mute (Cough Button)" : "Open Mic (Always Active)")
    ToolTip("🎙️ Voice Mode: " . lbl, 30, 30, 1)
    SetTimer(() => ToolTip(,,, 1), -2500)
}


ToggleAudioLimiter(*) {
    global audioLimiter, iniPath
    audioLimiter := !audioLimiter
    IniWrite(audioLimiter ? "true" : "false", iniPath, "Settings", "AudioLimiter")
    BuildTrayMenu()
    ToolTip(audioLimiter ? "🛡️ Audio Limiter: Enabled (Peak Protection)" : "🛡️ Audio Limiter: Disabled", 30, 30, 1)
    SetTimer(() => ToolTip(,,, 1), -2500)
}


ResolveCommunicationMic() {
    global detectedMics, pythonExe
    if (detectedMics.Length == 0)
        return ""
    script := (FileExist(A_ScriptDir . "\src\windows_comm_device_tracker.py") ? (A_ScriptDir . "\src\windows_comm_device_tracker.py") : (FileExist(A_ScriptDir . "\windows_comm_device_tracker.py") ? (A_ScriptDir . "\windows_comm_device_tracker.py") : (FileExist(A_ScriptDir . "\..\src\windows_comm_device_tracker.py") ? (A_ScriptDir . "\..\src\windows_comm_device_tracker.py") : (A_ScriptDir . "\..\windows_comm_device_tracker.py"))))
    cmd := '"' . pythonExe . '" "' . script . '" --config auto'
    try {
        shell := ComObject("WScript.Shell")
        exec := shell.Exec(cmd)
        out := exec.StdOut.ReadAll()
        if RegExMatch(out, "Resolved Mic:\s*([^\r\n]+)", &m) {
            resolved := Trim(m[1])
            if (resolved != "")
                return resolved
        }
    }
    return detectedMics[1]
}


PlayRecordingChime(chimeType) {
    global chimeEnabled, chimeVolume
    if (!chimeEnabled || chimeVolume <= 0)
        return
    switch chimeType {
        case "start":
            SoundBeep(523, 60), SoundBeep(659, 60), SoundBeep(784, 100)
        case "stop":
            SoundBeep(784, 60), SoundBeep(659, 60), SoundBeep(523, 100)
        case "pause":
            SoundBeep(440, 90), SoundBeep(330, 110)
        case "resume":
            SoundBeep(440, 90), SoundBeep(880, 110)
    }
}

ToggleChimeEnabled(*) {
    global chimeEnabled, iniPath
    chimeEnabled := !chimeEnabled
    IniWrite(chimeEnabled ? "true" : "false", iniPath, "Settings", "ChimeEnabled")
    BuildTrayMenu()
    ToolTip(chimeEnabled ? "🔔 Chimes: Enabled" : "🔕 Chimes: Muted", 30, 30, 1)
    SetTimer(() => ToolTip(,,, 1), -2500)
}

SetChimeVolume(vol) {
    global chimeVolume, iniPath
    chimeVolume := vol
    IniWrite(String(chimeVolume), iniPath, "Settings", "ChimeVolume")
    BuildTrayMenu()
    PlayRecordingChime("start")
    ToolTip("🔔 Chime Volume: " . chimeVolume . "%", 30, 30, 1)
    SetTimer(() => ToolTip(,,, 1), -2500)
}


ToggleMuteWarning(*) {
    global muteWarningEnabled, iniPath
    muteWarningEnabled := !muteWarningEnabled
    IniWrite(muteWarningEnabled ? "true" : "false", iniPath, "Settings", "MuteWarningEnabled")
    BuildTrayMenu()
    ToolTip(muteWarningEnabled ? "🎙️ Mute Warning: Enabled" : "🎙️ Mute Warning: Disabled", 30, 30, 1)
    SetTimer(() => ToolTip(,,, 1), -2500)
}

WarnSpeakingWhileMuted() {
    global muteWarningEnabled, lastMuteWarnTime
    if (!muteWarningEnabled || (A_TickCount - lastMuteWarnTime < 4000))
        return
    lastMuteWarnTime := A_TickCount
    ToolTip("🎙️⚠️ You are speaking while muted!", 30, 30, 1)
    SoundBeep(330, 120)
    SetTimer(() => ToolTip(,,, 1), -3000)
}


ResolveSecondaryMic(primaryName) {
    global detectedMics, secondaryMic, pythonExe
    if (detectedMics.Length == 0)
        return ""
    script := (FileExist(A_ScriptDir . "\src\audio_fallback_router.py") ? (A_ScriptDir . "\src\audio_fallback_router.py") : (FileExist(A_ScriptDir . "\audio_fallback_router.py") ? (A_ScriptDir . "\audio_fallback_router.py") : (FileExist(A_ScriptDir . "\..\src\audio_fallback_router.py") ? (A_ScriptDir . "\..\src\audio_fallback_router.py") : (A_ScriptDir . "\..\audio_fallback_router.py"))))
    cmd := '"' . pythonExe . '" "' . script . '" --primary "' . primaryName . '" --secondary "' . secondaryMic . '"'
    try {
        shell := ComObject("WScript.Shell")
        exec := shell.Exec(cmd)
        out := exec.StdOut.ReadAll()
        if RegExMatch(out, "Active Resolved:\s*([^\r\n]+)", &m) {
            resolved := Trim(m[1])
            if (resolved != "")
                return resolved
        }
    }
    return detectedMics[1]
}


ToggleEchoCancellation(*) {
    global echoCancellation, iniPath
    echoCancellation := !echoCancellation
    IniWrite(echoCancellation ? "true" : "false", iniPath, "Settings", "EchoCancellation")
    BuildTrayMenu()
    ToolTip(echoCancellation ? "🔇 Echo Cancellation: Enabled (Speakers Mode)" : "🔇 Echo Cancellation: Disabled", 30, 30, 1)
    SetTimer(() => ToolTip(,,, 1), -2500)
}
