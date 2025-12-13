@echo off
REM 测试v2.30.6新增和修改的文件编译

echo ========================================
echo 测试编译 v2.30.6 文件
echo ========================================

call conda activate mintchat

echo.
echo [1/3] 编译 thread_pool_manager.py...
python -m py_compile src/utils/thread_pool_manager.py
if %errorlevel% neq 0 (
    echo [错误] thread_pool_manager.py 编译失败
    exit /b 1
)
echo [成功] thread_pool_manager.py 编译通过

echo.
echo [2/3] 编译 enhanced_cache.py...
python -m py_compile src/utils/enhanced_cache.py
if %errorlevel% neq 0 (
    echo [错误] enhanced_cache.py 编译失败
    exit /b 1
)
echo [成功] enhanced_cache.py 编译通过

echo.
echo [3/3] 编译 light_chat_window.py...
python -m py_compile src/gui/light_chat_window.py
if %errorlevel% neq 0 (
    echo [错误] light_chat_window.py 编译失败
    exit /b 1
)
echo [成功] light_chat_window.py 编译通过

echo.
echo ========================================
echo 所有文件编译通过！
echo ========================================

pause

