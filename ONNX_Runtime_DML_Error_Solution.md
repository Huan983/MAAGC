# ONNX Runtime DirectML 错误解决方案

## 错误分析

错误信息：
```
Exception during initialization: D:\a\MaaDeps\MaaDeps\vcpkg\buildtrees\maa-onnxruntime\src\v1.19.2-da0b7a9dc3.clean\onnxruntime\core\providers\dml\DmlExecutionProvider\src\MLOperatorAuthorImpl.cpp(2813)\onnxruntime_maa.dll!00007FFC126F8E59: (caller: 00007FFC12715771) Exception(1) tid(7564) 80070057
```

**错误代码**：80070057（参数错误）
**错误来源**：ONNX Runtime DirectML (DML) 执行提供程序初始化失败

## 可能原因

1. **DirectX 12 兼容性问题**
2. **显卡驱动过时**
3. **ONNX 模型文件损坏**
4. **GPU 硬件不支持**
5. **系统资源不足**

## 解决方案

### 1. 检查 DirectX 12 支持

**步骤**：
- 按下 `Win + R` 键，输入 `dxdiag` 并回车
- 在打开的 DirectX 诊断工具中，查看 "系统信息" 部分的 "DirectX 版本"
- 确保版本为 **DirectX 12** 或更高

**如果不支持**：
- 升级 Windows 系统到 Windows 10 1709 或更高版本
- 或修改 MAA 配置使用 CPU 执行

### 2. 更新显卡驱动

**步骤**：
- 根据显卡品牌访问相应官网下载最新驱动：
  - NVIDIA: https://www.nvidia.com/Download/index.aspx
  - AMD: https://www.amd.com/zh-hans/support
  - Intel: https://www.intel.cn/content/www/cn/zh/support/detect.html
- 安装驱动并重启电脑

### 3. 验证并重新下载 OCR 模型

**步骤**：
1. 检查模型文件是否存在：
   ```
   f:\workspace\MAAGC\assets\MaaCommonAssets\OCR\
   ```
   确保包含 `det.onnx` 和 `rec.onnx` 文件

2. 重新下载模型：
   - 从 MAA 官方仓库下载最新 OCR 资源包
   - 或使用项目中提供的转换脚本重新生成模型

### 4. 修改 MAA 配置使用 CPU 执行

**步骤**：
1. 查找 MAA 配置文件（通常在 `config` 目录下）
2. 添加或修改以下配置，强制使用 CPU 执行提供程序：
   ```json
   {
     "OCR": {
       "Provider": "CPU"
     }
   }
   ```

### 5. 检查系统资源

**步骤**：
- 关闭其他占用大量 GPU 资源的程序（如游戏、视频编辑软件等）
- 确保系统内存充足（建议至少 8GB RAM）
- 清理临时文件，释放磁盘空间

### 6. 尝试降级 ONNX Runtime 版本

如果以上方法都不生效，可以尝试降级 ONNX Runtime 版本：

```bash
pip install onnxruntime==1.16.3
```

## 验证解决方案

**验证步骤**：
1. 重启 MAAGC 应用
2. 执行之前报错的任务
3. 检查日志是否还有类似错误

## 额外帮助

如果问题仍然存在：
- 查看 MAAGC 项目的 [GitHub Issues](https://github.com/MaaXYZ/MAAGC/issues) 寻找类似问题
- 加入 MAAGC QQ 群（123456789）寻求帮助
- 提供完整的日志文件和系统信息以便进一步分析

## 预防措施

1. 定期更新显卡驱动
2. 确保使用最新版本的 MAAGC 和 OCR 资源
3. 避免在资源紧张的环境下运行 MAAGC
4. 使用推荐的分辨率（1280x720）以获得最佳性能