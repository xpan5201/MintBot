#!/usr/bin/env python3
"""
性能优化脚本 v2.29.13
针对热点代码路径进行性能优化
"""

import re
from pathlib import Path
from typing import List, Dict, Tuple

PROJECT_ROOT = Path(__file__).parent.parent


class PerformanceOptimizer:
    """性能优化器"""
    
    def __init__(self):
        self.optimizations = []
        
    def optimize_string_concatenation(self, file_path: Path) -> int:
        """优化字符串拼接"""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.split('\n')
        
        optimized = 0
        new_lines = []
        in_loop = False
        loop_indent = 0
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            current_indent = len(line) - len(line.lstrip())
            
            # 检测循环开始
            if re.match(r'^\s*(for|while)\s+', line):
                in_loop = True
                loop_indent = current_indent
            # 检测循环结束
            elif in_loop and current_indent <= loop_indent and stripped:
                in_loop = False
            
            # 在循环中检测字符串拼接
            if in_loop and '+=' in line and ('"' in line or "'" in line):
                # 添加注释提示
                if i > 0 and '# TODO: 优化字符串拼接' not in lines[i-1]:
                    new_lines.append(f"{' ' * current_indent}# TODO: 优化字符串拼接，使用join()或列表")
                    optimized += 1
            
            new_lines.append(line)
        
        if optimized > 0:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(new_lines))
        
        return optimized
    
    def optimize_regex_compilation(self, file_path: Path) -> int:
        """优化正则表达式编译"""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 查找重复的正则表达式
        regex_patterns = re.findall(r're\.(search|match|findall|sub)\(["\'](.+?)["\']\)', content)
        pattern_counts = {}
        for method, pattern in regex_patterns:
            if pattern not in pattern_counts:
                pattern_counts[pattern] = 0
            pattern_counts[pattern] += 1
        
        # 找出重复使用的模式
        repeated_patterns = {p: c for p, c in pattern_counts.items() if c > 1}
        
        if repeated_patterns:
            print(f"  发现 {len(repeated_patterns)} 个重复的正则表达式模式")
            for pattern, count in repeated_patterns.items():
                print(f"    - '{pattern[:50]}...' 使用了 {count} 次")
        
        return len(repeated_patterns)
    
    def check_cache_usage(self, file_path: Path) -> Dict[str, int]:
        """检查缓存使用情况"""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        stats = {
            'cache_get': len(re.findall(r'\.get\(|cache\.get|_cache\[', content)),
            'cache_set': len(re.findall(r'\.set\(|cache\.set|_cache\[.*\]\s*=', content)),
            'cache_check': len(re.findall(r'if.*in.*cache|if.*cache\.get', content)),
        }
        
        return stats
    
    def analyze_hot_paths(self) -> List[Tuple[Path, str]]:
        """分析热点代码路径"""
        hot_paths = []
        
        # 核心模块
        core_modules = [
            PROJECT_ROOT / "src" / "agent" / "core.py",
            PROJECT_ROOT / "src" / "agent" / "memory.py",
            PROJECT_ROOT / "src" / "utils" / "async_vector_search.py",
            PROJECT_ROOT / "src" / "gui" / "light_chat_window.py",
        ]
        
        for module in core_modules:
            if module.exists():
                hot_paths.append((module, "核心模块"))
        
        return hot_paths
    
    def run_optimization(self):
        """运行优化"""
        print("=" * 60)
        print("  性能优化分析 v2.29.13")
        print("=" * 60)
        print()
        
        hot_paths = self.analyze_hot_paths()
        
        print(f"📊 分析 {len(hot_paths)} 个热点模块...\n")
        
        total_string_opts = 0
        total_regex_opts = 0
        
        for file_path, category in hot_paths:
            print(f"🔍 {file_path.name} ({category})")
            
            # 检查字符串拼接
            string_opts = self.optimize_string_concatenation(file_path)
            if string_opts > 0:
                print(f"  ⚠️  发现 {string_opts} 处字符串拼接可优化")
                total_string_opts += string_opts
            
            # 检查正则表达式
            regex_opts = self.optimize_regex_compilation(file_path)
            total_regex_opts += regex_opts
            
            # 检查缓存使用
            cache_stats = self.check_cache_usage(file_path)
            if cache_stats['cache_get'] > 0:
                print(f"  ✅ 缓存使用: get={cache_stats['cache_get']}, "
                      f"set={cache_stats['cache_set']}, check={cache_stats['cache_check']}")
            
            print()
        
        print("=" * 60)
        print("  优化建议总结")
        print("=" * 60)
        print(f"  字符串拼接优化: {total_string_opts} 处")
        print(f"  正则表达式优化: {total_regex_opts} 处")
        print()
        
        if total_string_opts > 0:
            print("💡 建议:")
            print("  - 循环中的字符串拼接改用 join() 或列表累积")
            print("  - 使用 f-string 替代 + 拼接")
            print()
        
        if total_regex_opts > 0:
            print("💡 建议:")
            print("  - 将重复使用的正则表达式预编译为模块级常量")
            print("  - 示例: PATTERN = re.compile(r'...')")
            print()


def main():
    optimizer = PerformanceOptimizer()
    optimizer.run_optimization()


if __name__ == "__main__":
    main()

