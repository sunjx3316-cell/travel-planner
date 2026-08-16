# 使用 Windows 系统 OCR(Windows.Media.Ocr)读取图片文字。
# 用法: powershell -ExecutionPolicy Bypass -File scripts\ocr.ps1 <图片路径>
param([string]$ImagePath)

$ErrorActionPreference = "Stop"

# 加载 WinRT 互操作程序集
try {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
} catch {
    Write-Host "无法加载 System.Runtime.WindowsRuntime: $($_.Exception.Message)"
    exit 3
}

if (-not $ImagePath -or -not (Test-Path $ImagePath)) {
    Write-Host "用法: powershell -File scripts\ocr.ps1 <图片路径>"
    exit 1
}
$ImagePath = (Resolve-Path $ImagePath).Path

# WinRT 异步转 .NET Task
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType = WindowsRuntime]
$getAwaiter = [System.WindowsRuntimeSystemExtensions].GetMethods() |
    Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } |
    Select-Object -First 1

function Await($WinRtTask, $ResultType) {
    $asTask = $getAwaiter.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    return $netTask.Result
}

$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($ImagePath)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])

$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if ($null -eq $engine) {
    Write-Host "系统无可用 OCR 语言包(需安装中文/英文语言包)"
    exit 2
}
Write-Host "OCR 语言: $($engine.RecognizerLanguage.DisplayName)"

$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
foreach ($line in $result.Lines) {
    Write-Host $line.Text
}
