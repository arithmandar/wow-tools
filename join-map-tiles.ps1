param(
    [Parameter(Mandatory = $true)]
    [string]$Directory,

    [Parameter(Mandatory = $true)]
    [string]$Prefix,

    [Parameter(Mandatory = $true)]
    [string]$OutputPath,

    [int]$Columns = 15,
    [int]$Rows = 10
)

$ErrorActionPreference = 'Stop'

if ($Columns -le 0 -or $Rows -le 0) {
    throw 'Columns and Rows must be greater than zero.'
}

$sourceDirectory = (Resolve-Path -LiteralPath $Directory).Path
$outputFile = [System.IO.Path]::GetFullPath($OutputPath)
if ([System.IO.Path]::GetExtension($outputFile) -ne '.png') {
    throw 'OutputPath must have a .png extension.'
}

$tilePattern = '^' + [regex]::Escape($Prefix) + '(\d+)\.png$'
$tiles = @(
    Get-ChildItem -LiteralPath $sourceDirectory -File -Filter "$Prefix*.png" |
        ForEach-Object {
            if ($_.Name -match $tilePattern) {
                [pscustomobject]@{
                    Index = [int]$Matches[1]
                    Path  = $_.FullName
                }
            }
        } |
        Sort-Object -Property Index
)

$expectedCount = $Columns * $Rows
if ($tiles.Count -ne $expectedCount) {
    throw "Expected $expectedCount tiles ($Columns columns x $Rows rows), found $($tiles.Count)."
}

for ($index = 0; $index -lt $expectedCount; $index++) {
    if ($tiles[$index].Index -ne $index) {
        throw "Missing tile index $index; tile filenames must be numbered contiguously from 0."
    }
    if ([string]::Equals(
            $tiles[$index].Path,
            $outputFile,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
        throw 'OutputPath must not overwrite an input tile.'
    }
}

Add-Type -AssemblyName System.Drawing

$firstTile = [System.Drawing.Image]::FromFile($tiles[0].Path)
try {
    $tileWidth = $firstTile.Width
    $tileHeight = $firstTile.Height
}
finally {
    $firstTile.Dispose()
}

$canvas = New-Object System.Drawing.Bitmap(
    ($tileWidth * $Columns),
    ($tileHeight * $Rows),
    [System.Drawing.Imaging.PixelFormat]::Format32bppArgb
)
$graphics = [System.Drawing.Graphics]::FromImage($canvas)

try {
    $graphics.CompositingMode = [System.Drawing.Drawing2D.CompositingMode]::SourceCopy

    for ($index = 0; $index -lt $expectedCount; $index++) {
        $tile = [System.Drawing.Image]::FromFile($tiles[$index].Path)
        try {
            if ($tile.Width -ne $tileWidth -or $tile.Height -ne $tileHeight) {
                throw "Tile '$($tiles[$index].Path)' has dimensions $($tile.Width)x$($tile.Height); expected ${tileWidth}x${tileHeight}."
            }

            $x = ($index % $Columns) * $tileWidth
            $y = [Math]::Floor($index / $Columns) * $tileHeight
            $graphics.DrawImage($tile, [int]$x, [int]$y, $tileWidth, $tileHeight)
        }
        finally {
            $tile.Dispose()
        }
    }

    $canvas.Save($outputFile, [System.Drawing.Imaging.ImageFormat]::Png)
}
finally {
    $graphics.Dispose()
    $canvas.Dispose()
}

Write-Output "Created $outputFile ($($tileWidth * $Columns)x$($tileHeight * $Rows))."
