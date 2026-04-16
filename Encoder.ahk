#Requires AutoHotkey v2.0
#SingleInstance Force

; ============================================================
;  Compresor.ahk  -  HandBrake Watch Encoder
;  Compile with Ahk2Exe for a standalone portable .exe
;  - Config is saved to compresor.ini next to the .exe
;  - Closing the window minimises to system tray
;  - Right-click tray icon to Show or Exit
;  - HandBrakeCLI.exe and ffprobe.exe are embedded in the .exe
;    and extracted to %LocalAppData%\Compresor\ on first run
;
;  IMPORTANT: Before compiling, place HandBrakeCLI.exe and
;  ffprobe.exe in the same folder as this .ahk file so that
;  Ahk2Exe can embed them via FileInstall().
; ============================================================

; ── Settings file (same folder as the .exe / .ahk) ───────────
global IniFile := A_ScriptDir . "\compresor.ini"

; ── Embedded binaries ─────────────────────────────────────────
; FileInstall embeds the files into the compiled .exe at build time.
; At runtime they are extracted to %LocalAppData%\Compresor\ once
; and reused on subsequent launches.
; When running as an uncompiled .ahk the files are used directly
; from the script folder so development works without recompiling.
global EmbedDir := A_AppData . "\Compresor"
global EmbedHB  := EmbedDir  . "\HandBrakeCLI.exe"
global EmbedFF  := EmbedDir  . "\ffprobe.exe"

if A_IsCompiled {
    DirCreate(EmbedDir)
    if !FileExist(EmbedHB)
        FileInstall("HandBrakeCLI.exe", EmbedHB, 0)
    if !FileExist(EmbedFF)
        FileInstall("ffprobe.exe",      EmbedFF, 0)
} else {
    EmbedHB := A_ScriptDir . "\HandBrakeCLI.exe"
    EmbedFF := A_ScriptDir . "\ffprobe.exe"
}

; ── Global State ─────────────────────────────────────────────
global AppState      := "idle"
global FileQueue     := []
global DoneFiles     := Map()
global HBPid         := 0
global CurFile       := ""
global CurOutputDir  := ""
global CurFileName   := ""
global CurFileBase   := ""
global CurOrigSize   := 0
global TempEncoded   := ""
global TempLog       := A_Temp . "\compresor_hb_stderr.txt"
global TempStdout    := A_Temp . "\compresor_hb_stdout.txt"
global StatsTotal    := 0
global StatsEncoded  := 0
global StatsCopied   := 0
global StatsSkipped  := 0
global VideoExtMap   := Map()
global LockRetries   := 0
global LockNextTry   := 0

; ── Layout Constants ─────────────────────────────────────────
MARGIN     := 8
FIELD_X    := 145
BROWSE_W   := 46
BROWSE_GAP := 4
LOG_Y      := 418

; ── Load saved settings (with defaults) ──────────────────────
LoadedSourceBase   := IniRead(IniFile, "Config", "SourceBase",   "C:\")
LoadedOutputBase   := IniRead(IniFile, "Config", "OutputBase",   "C:\")
LoadedHandBrakeCLI := IniRead(IniFile, "Config", "HandBrakeCLI", EmbedHB)
LoadedFFProbe      := IniRead(IniFile, "Config", "FFProbe",      EmbedFF)
LoadedTargetKbps   := IniRead(IniFile, "Config", "TargetKbps",   "1128")
LoadedOutWidth     := IniRead(IniFile, "Config", "OutWidth",     "1280")
LoadedOutHeight    := IniRead(IniFile, "Config", "OutHeight",    "720")
LoadedEncoder      := IniRead(IniFile, "Config", "Encoder",      "NVENC H.265 (GPU)")
LoadedDeleteSource := IniRead(IniFile, "Config", "DeleteSource", "1")
LoadedVideoExts    := IniRead(IniFile, "Config", "VideoExts",
    ".mkv .mp4 .avi .mov .wmv .m4v .ts .flv .mpg .mpeg")

; ── GUI Build ────────────────────────────────────────────────
G := Gui("+Resize +MinSize564x500", "Compresor  -  HandBrake Watch Encoder")
G.SetFont("s9", "Segoe UI")
G.MarginX := MARGIN
G.MarginY := MARGIN

GrpConfig := G.Add("GroupBox", "x8 y5 w548 h279", "Configuration")

G.Add("Text",  "x20 y28  w120 h20 +Right", "Source Folder:")
CtlSource    := G.Add("Edit",   "x145 y26  w355 h22 vSourceBase",   LoadedSourceBase)
BtnBrowseSrc := G.Add("Button", "x505 y25  w46  h24", "Browse")
BtnBrowseSrc.OnEvent("Click", BrowseSource)

G.Add("Text",  "x20 y56  w120 h20 +Right", "Output Folder:")
CtlOutput    := G.Add("Edit",   "x145 y54  w355 h22 vOutputBase",   LoadedOutputBase)
BtnBrowseOut := G.Add("Button", "x505 y53  w46  h24", "Browse")
BtnBrowseOut.OnEvent("Click", BrowseOutput)

G.Add("Text",  "x20 y84  w120 h20 +Right", "HandBrakeCLI.exe:")
CtlHB        := G.Add("Edit",   "x145 y82  w355 h22 vHandBrakeCLI", LoadedHandBrakeCLI)
BtnBrowseHB  := G.Add("Button", "x505 y81  w46  h24", "Browse")
BtnBrowseHB.OnEvent("Click", BrowseHB)

G.Add("Text",  "x20 y112 w120 h20 +Right", "ffprobe.exe:")
CtlFF        := G.Add("Edit",   "x145 y110 w355 h22 vFFProbe",      LoadedFFProbe)
BtnBrowseFF  := G.Add("Button", "x505 y109 w46  h24", "Browse")
BtnBrowseFF.OnEvent("Click", BrowseFF)

G.Add("Text",  "x20 y140 w120 h20 +Right", "Target Kbps:")
CtlKbps      := G.Add("Edit",   "x145 y138 w70  h22 vTargetKbps",  LoadedTargetKbps)
G.Add("Text",  "x222 y140 w200 h20", "(video 1000  +  audio 128)")

G.Add("Text",  "x20 y168 w120 h20 +Right", "Output Resolution:")
CtlResW      := G.Add("Edit",   "x145 y166 w60  h22 vOutWidth",    LoadedOutWidth)
G.Add("Text",  "x210 y168 w14  h20 +Center", "x")
CtlResH      := G.Add("Edit",   "x226 y166 w60  h22 vOutHeight",   LoadedOutHeight)
G.Add("Text",  "x292 y168 w180 h20", "(width x height in pixels)")

G.Add("Text",  "x20 y196 w120 h20 +Right", "Video Extensions:")
CtlExts      := G.Add("Edit",   "x145 y194 w355 h22 vVideoExts",   LoadedVideoExts)

G.Add("Text",  "x20 y224 w120 h20 +Right", "Encoder:")
CtlEncoder   := G.Add("DropDownList", "x145 y222 w200 h100 vEncoder",
    ["NVENC H.265 (GPU)", "x265 (CPU - Best Quality)", "x264 (CPU - Fast)"])
CtlEncoder.Choose(LoadedEncoder)
if CtlEncoder.Value = 0
    CtlEncoder.Choose(1)
G.Add("Text",  "x352 y224 w200 h20", "(NVENC requires Nvidia GPU)")

G.Add("Text",  "x20 y252 w120 h20 +Right", "After Processing:")
CtlDelete    := G.Add("Checkbox", "x145 y252 w250 h20 vDeleteSource", "Delete source file when done")
CtlDelete.Value := Integer(LoadedDeleteSource)

; ── Register change events to auto-save (debounced) ──────────
for ctl in [CtlSource, CtlOutput, CtlHB, CtlFF, CtlKbps, CtlResW, CtlResH, CtlExts]
    ctl.OnEvent("Change", DebounceSave)
CtlEncoder.OnEvent("Change", DebounceSave)
CtlDelete.OnEvent("Click",   DebounceSave)

; ── Buttons ───────────────────────────────────────────────────
BtnStart := G.Add("Button", "x8   y292 w100 h32", "▶   Start")
BtnStart.SetFont("s10 Bold")
BtnStart.OnEvent("Click", StartEncoder)

BtnStop  := G.Add("Button", "x116 y292 w100 h32", "■   Stop")
BtnStop.SetFont("s10")
BtnStop.Enabled := false
BtnStop.OnEvent("Click", StopEncoder)

BtnClear := G.Add("Button", "x480 y292 w76 h32", "Clear Log")
BtnClear.OnEvent("Click", (*) => (CtlLog.Value := "", CtlProgress.Value := ""))

; ── Status / Stats / Progress ────────────────────────────────
CtlStatus := G.Add("Text", "x8 y332 w548 h22", "Status:  Ready")
CtlStatus.SetFont("s9 Bold")

CtlStats  := G.Add("Text", "x8 y354 w548 h18",
    "Processed: 0   Encoded: 0   Copied: 0   Skipped: 0   Queued: 0")
CtlStats.SetFont("s8", "Consolas")

CtlProgress := G.Add("Edit", "x8 y376 w548 h20 ReadOnly -VScroll", "")
CtlProgress.SetFont("s8", "Consolas")

G.Add("Text", "x8 y402 w200 h16", "Activity Log:")
CtlLog := G.Add("Edit", "x8 y418 w548 h260 ReadOnly -Wrap +VScroll")
CtlLog.SetFont("s8", "Consolas")

G.Show("w564 h686")
G.OnEvent("Close", WindowClose)
G.OnEvent("Size",  ResizeLayout)

; ── Tray Setup ───────────────────────────────────────────────
A_TrayMenu.Delete()
A_TrayMenu.Add("Show Compresor", TrayShow)
A_TrayMenu.Add("Exit",           TrayExit)
A_TrayMenu.Default := "Show Compresor"
TraySetIcon(A_AhkPath, 2)
A_IconTip := "Compresor - HandBrake Watch Encoder"

; ── Window Close -> Minimise to Tray ────────────────────────
WindowClose(*) {
    global G
    G.Hide()
    TrayTip("Compresor", "Running in the background. Right-click the tray icon to show or exit.", 3)
}

TrayShow(*) {
    global G
    G.Show()
}

TrayExit(*) {
    global HBPid
    if HBPid && ProcessExist(HBPid) {
        if MsgBox("An encode is running. Are you sure you want to exit?",
                  "Compresor", "YesNo Icon!") != "Yes"
            return
        ProcessClose(HBPid)
    }
    SetTimer(DriveEngine, 0)
    ExitApp()
}

; ── Resize Handler ───────────────────────────────────────────
ResizeLayout(thisGui, minMax, clientW, clientH) {
    if (minMax = -1)
        return

    browseX    := clientW - MARGIN - BROWSE_W
    editW_br   := browseX - BROWSE_GAP - FIELD_X
    editW_full := clientW - MARGIN - FIELD_X - MARGIN
    fullW      := clientW - 2 * MARGIN
    clearX     := clientW - MARGIN - 76
    logH       := clientH - LOG_Y - MARGIN
    if (logH < 60)
        logH := 60

    GrpConfig.Move(,    , fullW)
    CtlSource.Move(,    , editW_br)
    CtlOutput.Move(,    , editW_br)
    CtlHB.Move(,        , editW_br)
    CtlFF.Move(,        , editW_br)
    BtnBrowseSrc.Move(browseX)
    BtnBrowseOut.Move(browseX)
    BtnBrowseHB.Move(browseX)
    BtnBrowseFF.Move(browseX)
    CtlExts.Move(,      , editW_full)
    BtnClear.Move(clearX)
    CtlStatus.Move(,    , fullW)
    CtlStats.Move(,     , fullW)
    CtlProgress.Move(,  , fullW)
    CtlLog.Move(,       , fullW, logH)
}

; ── Debounced Settings Save ──────────────────────────────────
DebounceSave(*) {
    SetTimer(DoSaveSettings, -500)
}

DoSaveSettings() {
    global G, IniFile
    s := G.Submit(false)
    IniWrite(s.SourceBase,   IniFile, "Config", "SourceBase")
    IniWrite(s.OutputBase,   IniFile, "Config", "OutputBase")
    IniWrite(s.HandBrakeCLI, IniFile, "Config", "HandBrakeCLI")
    IniWrite(s.FFProbe,      IniFile, "Config", "FFProbe")
    IniWrite(s.TargetKbps,   IniFile, "Config", "TargetKbps")
    IniWrite(s.OutWidth,     IniFile, "Config", "OutWidth")
    IniWrite(s.OutHeight,    IniFile, "Config", "OutHeight")
    IniWrite(s.Encoder,      IniFile, "Config", "Encoder")
    IniWrite(s.DeleteSource, IniFile, "Config", "DeleteSource")
    IniWrite(s.VideoExts,    IniFile, "Config", "VideoExts")
}

; ── Helpers ──────────────────────────────────────────────────
AppLog(msg) {
    global CtlLog, CtlStatus
    ts := FormatTime(, "yyyy-MM-dd HH:mm:ss")
    CtlLog.Value .= "[" . ts . "] " . msg . "`n"
    SendMessage(0x115, 7, 0, CtlLog)
    CtlStatus.Value := "Status:  " . msg
}

FmtSize(bytes) => Round(bytes / 1048576, 2) . " MB"

UpdateStats() {
    global CtlStats, StatsTotal, StatsEncoded, StatsCopied, StatsSkipped, FileQueue
    CtlStats.Value := "Processed: " . StatsTotal
        . "   Encoded: "  . StatsEncoded
        . "   Copied: "   . StatsCopied
        . "   Skipped: "  . StatsSkipped
        . "   Queued: "   . FileQueue.Length
}

IsVideoFile(path) {
    global VideoExtMap
    SplitPath(path, , , &ext)
    return VideoExtMap.Has("." . StrLower(ext))
}

GetVideoExts() {
    global G
    saved := G.Submit(false)
    parts := StrSplit(Trim(saved.VideoExts), " ")
    result := Map()
    for p in parts {
        p := Trim(StrLower(p))
        if p != ""
            result[p] := true
    }
    return result
}

RunFFProbe(ffprobe, args) {
    tmp := A_Temp . "\compresor_ffprobe_" . A_TickCount . ".txt"
    RunWait('cmd /c "' . ffprobe . '" ' . args . ' 2>nul >"' . tmp . '"',, "Hide")
    result := ""
    try result := Trim(FileRead(tmp))
    try FileDelete(tmp)
    return result
}

GetConfig() {
    global G
    s := G.Submit(false)
    encoderMap := Map(
        "NVENC H.265 (GPU)",         {flag: "nvenc_h265", label: "NVENC H.265 (GPU)"},
        "x265 (CPU - Best Quality)", {flag: "x265",       label: "x265 (CPU)"},
        "x264 (CPU - Fast)",         {flag: "x264",       label: "x264 (CPU)"}
    )
    encInfo := encoderMap.Has(s.Encoder) ? encoderMap[s.Encoder]
             : {flag: "nvenc_h265", label: "NVENC H.265 (GPU)"}

    targetKbps := 1128
    outWidth   := 1280
    outHeight  := 720
    try targetKbps := Integer(s.TargetKbps)
    try outWidth   := Integer(s.OutWidth)
    try outHeight  := Integer(s.OutHeight)

    return {
        SourceBase:   RTrim(s.SourceBase,  "\"),
        OutputBase:   RTrim(s.OutputBase,  "\"),
        HandBrakeCLI: s.HandBrakeCLI,
        FFProbe:      s.FFProbe,
        TargetKbps:   targetKbps,
        OutWidth:     outWidth,
        OutHeight:    outHeight,
        DeleteSource: s.DeleteSource,
        EncoderFlag:  encInfo.flag,
        EncoderLabel: encInfo.label
    }
}

; ── Browse Buttons ───────────────────────────────────────────
BrowseSource(*) {
    global CtlSource
    p := DirSelect(, 3, "Select Source Watch Folder")
    if p
        CtlSource.Value := p
}
BrowseOutput(*) {
    global CtlOutput
    p := DirSelect(, 3, "Select Output Root Folder")
    if p
        CtlOutput.Value := p
}
BrowseHB(*) {
    global CtlHB
    p := FileSelect(, EmbedDir . "\", "Select HandBrakeCLI.exe", "Executable (*.exe)")
    if p
        CtlHB.Value := p
}
BrowseFF(*) {
    global CtlFF
    p := FileSelect(, EmbedDir . "\", "Select ffprobe.exe", "Executable (*.exe)")
    if p
        CtlFF.Value := p
}

; ── Start / Stop ─────────────────────────────────────────────
StartEncoder(*) {
    global AppState, FileQueue, DoneFiles, BtnStart, BtnStop
    global StatsTotal, StatsEncoded, StatsCopied, StatsSkipped, VideoExtMap

    if (AppState != "idle")
        return

    cfg := GetConfig()

    if !DirExist(cfg.SourceBase) {
        MsgBox("Source folder not found:`n" . cfg.SourceBase, "Compresor", "Icon! T5")
        return
    }
    if !FileExist(cfg.HandBrakeCLI) {
        MsgBox("HandBrakeCLI.exe not found:`n" . cfg.HandBrakeCLI, "Compresor", "Icon! T5")
        return
    }
    if !FileExist(cfg.FFProbe) {
        MsgBox("ffprobe.exe not found:`n" . cfg.FFProbe, "Compresor", "Icon! T5")
        return
    }

    VideoExtMap    := GetVideoExts()
    DoneFiles      := Map()
    FileQueue      := []
    StatsTotal     := 0
    StatsEncoded   := 0
    StatsCopied    := 0
    StatsSkipped   := 0
    BtnStart.Enabled := false
    BtnStop.Enabled  := true

    AppLog("==================================================")
    AppLog("Compresor started")
    AppLog("HandBrakeCLI : " . cfg.HandBrakeCLI)
    AppLog("ffprobe      : " . cfg.FFProbe)
    AppLog("Source  : " . cfg.SourceBase)
    AppLog("Output  : " . cfg.OutputBase)
    AppLog("Target  : " . cfg.TargetKbps . " kbps  |  " . cfg.OutWidth . "x" . cfg.OutHeight . "  |  " . cfg.EncoderLabel)
    AppLog("Delete source : " . (cfg.DeleteSource ? "Yes" : "No"))
    AppLog("==================================================")
    AppLog("Scanning source folder for existing files...")

    loop files cfg.SourceBase . "\*.*", "RF" {
        if IsVideoFile(A_LoopFileFullPath) {
            FileQueue.Push(A_LoopFileFullPath)
            DoneFiles[A_LoopFileFullPath] := true
        }
    }

    if FileQueue.Length > 0
        AppLog("Found " . FileQueue.Length . " existing file(s) to process.")
    else
        AppLog("No existing files found. Switching to watch mode.")

    UpdateStats()
    AppState := "processing"
    SetTimer(DriveEngine, 1000)
}

StopEncoder(*) {
    global AppState, HBPid, BtnStart, BtnStop, CtlProgress, TempEncoded

    SetTimer(DriveEngine, 0)

    if HBPid && ProcessExist(HBPid) {
        ProcessClose(HBPid)
        HBPid := 0
        try FileDelete(TempEncoded)
        AppLog("HandBrake process terminated.")
    }

    BtnStart.Enabled  := true
    BtnStop.Enabled   := false
    CtlProgress.Value := ""
    AppState := "idle"
    AppLog("Encoder stopped by user.")
}

; ── Main Engine ──────────────────────────────────────────────
DriveEngine() {
    global AppState, FileQueue, DoneFiles, HBPid, TempLog, CtlProgress
    global LockRetries, LockNextTry, CurFile, StatsSkipped

    if (AppState = "encoding") {
        if !ProcessExist(HBPid) {
            HBPid := 0
            CtlProgress.Value := ""
            OnEncodingComplete()
            return
        }
        try {
            f := FileOpen(TempLog, "r")
            fSize := f.Length
            if fSize > 4096
                f.Seek(-4096, 2)
            raw := f.Read()
            f.Close()
            lines := StrSplit(raw, "`r")
            i := lines.Length
            while i >= 1 {
                line := Trim(lines[i])
                if InStr(line, "Encoding:") = 1 {
                    CtlProgress.Value := line
                    break
                }
                i--
            }
        }
        return
    }

    if (AppState = "waiting_lock") {
        if (A_TickCount < LockNextTry)
            return
        try {
            f := FileOpen(CurFile, "r")
            f.Close()
        } catch {
            LockRetries--
            if (LockRetries <= 0) {
                AppLog("ERROR: File still locked after all retries. Skipping.")
                StatsSkipped++
                UpdateStats()
                AppState := "processing"
                return
            }
            AppLog("File locked, retrying in 5s... (" . LockRetries . " retries left)")
            LockNextTry := A_TickCount + 5000
            return
        }
        ProcessUnlockedFile()
        return
    }

    if (AppState = "processing") {
        if FileQueue.Length = 0 {
            AppState := "watching"
            AppLog("Queue empty. Watching for new files...")
            return
        }
        nextFile := FileQueue.RemoveAt(1)
        UpdateStats()
        BeginProcessFile(nextFile)
        return
    }

    if (AppState = "watching") {
        cfg   := GetConfig()
        found := 0
        loop files cfg.SourceBase . "\*.*", "RF" {
            path := A_LoopFileFullPath
            if IsVideoFile(path) && !DoneFiles.Has(path) {
                DoneFiles[path] := true
                FileQueue.Push(path)
                AppLog("New file detected: " . path)
                found++
            }
        }
        if found > 0 {
            UpdateStats()
            AppState := "processing"
        }
    }
}

; ── Process One File (pre-lock phase) ────────────────────────
BeginProcessFile(filePath) {
    global AppState, CurFile, StatsTotal, StatsSkipped
    global LockRetries, LockNextTry

    if !FileExist(filePath) {
        AppLog("File no longer exists, skipping: " . filePath)
        AppState := "processing"
        return
    }

    StatsTotal++
    UpdateStats()

    AppLog("------------------------------------------------------")
    AppLog("Processing : " . filePath)

    CurFile := filePath

    try {
        f := FileOpen(filePath, "r")
        f.Close()
    } catch {
        LockRetries := 11
        LockNextTry := A_TickCount + 5000
        AppLog("File locked, retrying in 5s... (11 retries left)")
        AppState := "waiting_lock"
        return
    }

    ProcessUnlockedFile()
}

; ── Process One File (post-lock phase) ───────────────────────
ProcessUnlockedFile() {
    global AppState, CurFile, CurOutputDir, CurFileName, CurFileBase
    global CurOrigSize, TempEncoded, TempLog, TempStdout, HBPid
    global StatsCopied, StatsSkipped

    filePath := CurFile
    cfg := GetConfig()

    relPath   := SubStr(filePath, StrLen(cfg.SourceBase) + 2)
    lastSlash := InStr(relPath, "\", , -1)
    if lastSlash {
        relDir   := SubStr(relPath, 1, lastSlash - 1)
        fileName := SubStr(relPath, lastSlash + 1)
    } else {
        relDir   := ""
        fileName := relPath
    }
    lastDot  := InStr(fileName, ".", , -1)
    fileBase := lastDot ? SubStr(fileName, 1, lastDot - 1) : fileName
    outputDir := cfg.OutputBase . (relDir != "" ? "\" . relDir : "")

    if !DirExist(outputDir) {
        DirCreate(outputDir)
        AppLog("Created output dir: " . outputDir)
    }

    origSize := FileGetSize(filePath)
    AppLog("Original size      : " . FmtSize(origSize))

    resOut := RunFFProbe(cfg.FFProbe,
        '-v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 "' . filePath . '"')
    width := 0, height := 0
    if RegExMatch(resOut, "(\d+),(\d+)", &m) {
        width  := Integer(m[1])
        height := Integer(m[2])
        AppLog("Resolution         : " . width . "x" . height)
    } else {
        AppLog("WARNING: Could not read resolution. Will attempt encoding.")
    }

    if (height > 0 && height < cfg.OutHeight) {
        AppLog("Resolution below output target -- copying original.")
        FileCopy(filePath, outputDir . "\" . fileName, 1)
        if cfg.DeleteSource
            FileDelete(filePath)
        StatsCopied++
        UpdateStats()
        AppLog("Copied original." . (cfg.DeleteSource ? " Source deleted." : " Source kept."))
        AppLog("------------------------------------------------------")
        AppState := "processing"
        return
    }

    durOut := RunFFProbe(cfg.FFProbe,
        '-v error -show_entries format=duration -of csv=p=0 "' . filePath . '"')
    duration := 0.0
    if RegExMatch(durOut, "[\d.]+")
        duration := Float(durOut)

    if (duration > 0) {
        origKbps  := Round((origSize * 8) / (duration * 1000), 1)
        predictMB := Round((cfg.TargetKbps * 1000 / 8) * duration / 1048576, 2)
        AppLog("Duration           : " . Round(duration, 1) . "s")
        AppLog("Original bitrate   : " . origKbps . " kbps")
        AppLog("Predicted output   : " . predictMB . " MB  (target " . cfg.TargetKbps . " kbps)")

        if (origKbps <= cfg.TargetKbps) {
            AppLog("Bitrate already at or below target -- copying original.")
            FileCopy(filePath, outputDir . "\" . fileName, 1)
            if cfg.DeleteSource
                FileDelete(filePath)
            StatsSkipped++
            UpdateStats()
            AppLog("Copied original." . (cfg.DeleteSource ? " Source deleted." : " Source kept."))
            AppLog("------------------------------------------------------")
            AppState := "processing"
            return
        }
    } else {
        AppLog("WARNING: Could not read duration. Proceeding with encode.")
    }

    stamp   := FormatTime(, "yyyyMMdd_HHmmss")
    tempOut := A_Temp . "\compresor_encoded_" . stamp . ".mkv"
    try FileDelete(tempOut)
    try FileDelete(TempLog)
    try FileDelete(TempStdout)
    FileAppend("", TempLog)
    FileAppend("", TempStdout)

    hbArgs := '-i "' . filePath . '" '
            . '-o "' . tempOut  . '" '
            . '--encoder ' . cfg.EncoderFlag . ' '
            . '--vb 1000 '
            . '--ab 128 '
            . '--aencoder av_aac '
            . '--width '  . cfg.OutWidth  . ' '
            . '--height ' . cfg.OutHeight . ' '
            . '--loose-anamorphic '
            . '--format av_mkv'

    CurOutputDir := outputDir
    CurFileName  := fileName
    CurFileBase  := fileBase
    CurOrigSize  := origSize
    TempEncoded  := tempOut

    AppLog("Encoding : " . cfg.EncoderLabel . " / ABR 1000kbps / " . cfg.OutWidth . "x" . cfg.OutHeight)

    cmdLine := 'cmd /c ""' . cfg.HandBrakeCLI . '" ' . hbArgs
             . ' 2>"' . TempLog . '" >"' . TempStdout . '""'
    Run(cmdLine,, "Hide", &pid)
    HBPid    := pid
    AppState := "encoding"
}

; ── After Encoding Completes ─────────────────────────────────
OnEncodingComplete() {
    global AppState, CurFile, CurOutputDir, CurFileName, CurFileBase
    global CurOrigSize, TempEncoded, StatsEncoded, StatsCopied

    cfg := GetConfig()

    if !FileExist(TempEncoded) || FileGetSize(TempEncoded) = 0 {
        AppLog("ERROR: Encoding produced no output. Falling back to original.")
        FileCopy(CurFile, CurOutputDir . "\" . CurFileName, 1)
        if cfg.DeleteSource
            FileDelete(CurFile)
        StatsCopied++
        UpdateStats()
        AppLog("Copied original." . (cfg.DeleteSource ? " Source deleted." : " Source kept."))
        AppLog("------------------------------------------------------")
        AppState := "processing"
        return
    }

    encodedSize := FileGetSize(TempEncoded)
    saving      := Round((1 - encodedSize / CurOrigSize) * 100, 1)
    AppLog("Encoded size       : " . FmtSize(encodedSize))

    if (encodedSize >= CurOrigSize) {
        AppLog("Encoded file LARGER than original (" . Abs(saving) . "% bigger). Using original.")
        FileDelete(TempEncoded)
        FileCopy(CurFile, CurOutputDir . "\" . CurFileName, 1)
        if cfg.DeleteSource
            FileDelete(CurFile)
        AppLog("Copied original to : " . CurOutputDir . "\" . CurFileName)
        StatsCopied++
    } else {
        finalOut := CurOutputDir . "\" . CurFileBase . ".mkv"
        FileMove(TempEncoded, finalOut, 1)
        if cfg.DeleteSource && FileExist(CurFile)
            FileDelete(CurFile)
        AppLog("Saved encoded file : " . finalOut)
        AppLog("Space saved        : " . saving . "%")
        StatsEncoded++
    }

    AppLog(cfg.DeleteSource ? "Source deleted     : " . CurFileName
                            : "Source kept        : " . CurFileName)
    AppLog("------------------------------------------------------")
    UpdateStats()
    AppState := "processing"
}
