@echo off
setlocal
if "%~1"=="" (echo Usage: build.cmd upstream-source-folder [loops] & exit /b 1)
if /i not "%VSCMD_ARG_TGT_ARCH%"=="x86" (echo Run from an x86 Native Tools Command Prompt for Visual Studio 2022. & exit /b 1)
if not exist "%~1\CMakeLists.txt" (echo Upstream source folder not found. & exit /b 1)
set "WDS_LOOP_OPTION=OFF"
set "WDS_BUILD_NAME=build-wds-animation-safety"
if /i "%~2"=="loops" (set "WDS_LOOP_OPTION=ON" & set "WDS_BUILD_NAME=build-wds-dance-loops")
set "_CL_=/Z7"
cmake -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo -DCMAKE_TRY_COMPILE_CONFIGURATION=Release -DCMAKE_MSVC_DEBUG_INFORMATION_FORMAT=Embedded -DASCENSION_ANIMATION_SAFETY=ON -DASCENSION_DANCE_LOOP_REGIONS=%WDS_LOOP_OPTION% -DCMAKE_C_FLAGS_DEBUG="/Ob0 /Od /RTC1 /Z7" -DCMAKE_CXX_FLAGS_DEBUG="/Ob0 /Od /RTC1 /Z7" -DCMAKE_EXE_LINKER_FLAGS_DEBUG="/INCREMENTAL:NO /DEBUG:NONE" -DCMAKE_SHARED_LINKER_FLAGS_RELWITHDEBINFO="/INCREMENTAL:NO /DEBUG:NONE" -DCMAKE_C_FLAGS_RELWITHDEBINFO="/O2 /Ob1 /DNDEBUG /Z7" -DCMAKE_CXX_FLAGS_RELWITHDEBINFO="/O2 /Ob1 /DNDEBUG /Z7" -S "%~1" -B "%~1\%WDS_BUILD_NAME%"
if errorlevel 1 exit /b 1
cmake --build "%~1\%WDS_BUILD_NAME%" --parallel 4
exit /b %errorlevel%
