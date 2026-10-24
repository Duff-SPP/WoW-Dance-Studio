@echo off
setlocal
if "%~1"=="" (echo Usage: test.cmd patched-upstream-source-folder & exit /b 1)
if /i not "%VSCMD_ARG_TGT_ARCH%"=="x86" (echo Run from an x86 Native Tools Command Prompt for Visual Studio 2022. & exit /b 1)
pushd "%~1"
if errorlevel 1 exit /b 1
if not exist build-wds-tests mkdir build-wds-tests
cl /nologo /std:c++17 /EHsc /Od /RTC1 /MTd /DASCENSION_ANIMATION_SAFETY=1 /Isrc tests\animation_safety_harness.cpp src\Ascension\AscAnimationSafety.cpp /Fe:build-wds-tests\animation_safety.exe /Fo:build-wds-tests\
if errorlevel 1 goto fail
build-wds-tests\animation_safety.exe
if errorlevel 1 goto fail
cl /nologo /EHsc /std:c++17 /Od /MTd tests\dance_loop_clock.cpp /Fe:build-wds-tests\dance_loop_clock.exe /Fo:build-wds-tests\dance_loop_clock.obj
if errorlevel 1 goto fail
build-wds-tests\dance_loop_clock.exe
if errorlevel 1 goto fail
cl /nologo /EHsc /std:c++17 /O2 /MTd /Isrc tests\dance_loop_sampler_harness.cpp /Fe:build-wds-tests\dance_loop_sampler.exe /Fo:build-wds-tests\dance_loop_sampler.obj
if errorlevel 1 goto fail
build-wds-tests\dance_loop_sampler.exe
if errorlevel 1 goto fail
popd
exit /b 0
:fail
popd
exit /b 1
