param(
    [int]$X,
    [int]$Y,
    [int]$Width,
    [int]$Height
)

# Use physical pixels so AHK regions match capture coordinates under display scaling.
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class DpiAwareness {
    [DllImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool SetProcessDpiAwarenessContext(IntPtr value);

    [DllImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool SetProcessDPIAware();
}
'@
try {
    if (-not [DpiAwareness]::SetProcessDpiAwarenessContext([IntPtr](-4))) {
        [DpiAwareness]::SetProcessDPIAware() | Out-Null
    }
} catch {
    try { [DpiAwareness]::SetProcessDPIAware() | Out-Null } catch {}
}

Add-Type -AssemblyName System.Drawing

$bitmap = New-Object System.Drawing.Bitmap $Width, $Height
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($X, $Y, 0, 0, (New-Object System.Drawing.Size $Width, $Height))
$graphics.Dispose()

$tempFile = [System.IO.Path]::GetTempFileName() + ".png"
$scale = 1
if ($Height -lt 150 -and $Width -lt 450) { $scale = 3 }
elseif ($Height -lt 300 -and $Width -lt 900) { $scale = 2 }
$scaled = New-Object System.Drawing.Bitmap ($Width * $scale), ($Height * $scale)
$sg = [System.Drawing.Graphics]::FromImage($scaled)
$sg.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$sg.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
$colorMatrix = New-Object System.Drawing.Imaging.ColorMatrix
$colorMatrix.Matrix00 = 0.405;  $colorMatrix.Matrix01 = 0.405;  $colorMatrix.Matrix02 = 0.405
$colorMatrix.Matrix10 = 0.7965; $colorMatrix.Matrix11 = 0.7965; $colorMatrix.Matrix12 = 0.7965
$colorMatrix.Matrix20 = 0.1485; $colorMatrix.Matrix21 = 0.1485; $colorMatrix.Matrix22 = 0.1485
$colorMatrix.Matrix33 = 1; $colorMatrix.Matrix40 = -0.175; $colorMatrix.Matrix41 = -0.175; $colorMatrix.Matrix42 = -0.175; $colorMatrix.Matrix44 = 1
$imageAttributes = New-Object System.Drawing.Imaging.ImageAttributes
$imageAttributes.SetColorMatrix($colorMatrix)
# Preserve antialiased game text; a hard threshold would destroy glow and outline detail.
$destination = New-Object System.Drawing.Rectangle 0, 0, ($Width * $scale), ($Height * $scale)
$sg.DrawImage($bitmap, $destination, 0, 0, $Width, $Height, [System.Drawing.GraphicsUnit]::Pixel, $imageAttributes)
$imageAttributes.Dispose()
$sg.Dispose()
$scaled.Save($tempFile, [System.Drawing.Imaging.ImageFormat]::Png)
$scaled.Dispose()
$bitmap.Dispose()

Add-Type -AssemblyName System.Runtime.WindowsRuntime

[Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null
[Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime] | Out-Null
[Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType = WindowsRuntime] | Out-Null

Function Await($WinRtTask, $ResultType) {
    $asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
    })[0]
    $asTaskGeneric = $asTask.MakeGenericMethod($ResultType)
    $task = $asTaskGeneric.Invoke($null, @($WinRtTask))
    $task.Wait(-1) | Out-Null
    $task.Result
}

try {
    $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($tempFile)) ([Windows.Storage.StorageFile])
    $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $softwareBitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])

    $ocrEngine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
    if ($null -eq $ocrEngine) {
        $ocrEngine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('en-US'))
    }
    if ($null -eq $ocrEngine) {
        Write-Output ""
    } else {
        $ocrResult = Await ($ocrEngine.RecognizeAsync($softwareBitmap)) ([Windows.Media.Ocr.OcrResult])
        Write-Output $ocrResult.Text
    }
} finally {
    Remove-Item $tempFile -ErrorAction SilentlyContinue
}
