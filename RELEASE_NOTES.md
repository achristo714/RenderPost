## Render Post v1.12.2

Fixed a build issue that broke the automated exe build (and would have broken a local
`build.bat` build too): PyInstaller's bundling step for the `mcp` package tried to import a part
of it RenderPost never uses (its command-line tool), which needed a package that wasn't installed.
No app behavior changes — this release exists only to get a working exe out again.

Nothing else changed since 1.12.1.
