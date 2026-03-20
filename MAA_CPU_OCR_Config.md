# MAA CPU OCR 配置指南

## 问题分析

您遇到的错误是ONNX Runtime在尝试使用DirectML(DML)执行提供程序时发生的初始化失败：
```
Exception during initialization: D:\a\MaaDeps\MaaDeps\vcpkg\buildtrees\maa-onnxruntime\src\v1.19.2-da0b7a9dc3.clean\onnxruntime\core\providers\dml\DmlExecutionProvider\src\MLOperatorAuthorImpl.cpp(2813)\onnxruntime_maa.dll!00007FFC12145771: (caller: 00007FFC12145771) Exception(1) tid(1b14) 80070057
```

错误代码`80070057`表示参数错误，这通常是由于DirectX 12兼容性问题或显卡驱动不兼容导致的。

## 解决方案：强制使用CPU执行OCR

### 方法1：创建MAA配置文件

1. 在MAA安装目录下创建或编辑配置文件 `config.json`
2. 添加以下内容，强制MAA使用CPU执行OCR：

```json
{
    "ocr": {
        "provider": "cpu"
    },
    "gpu": {
        "enabled": false
    }
}
```

### 方法2：使用命令行参数

启动MAA时添加以下命令行参数：

```bash
MaaAssistant.exe --ocr-provider cpu --disable-gpu
```

### 方法3：修改注册表（Windows）

如果MAA使用注册表存储配置，可以尝试以下操作：

1. 按下 `Win + R` 输入 `regedit` 打开注册表编辑器
2. 导航到 `HKEY_CURRENT_USER\Software\MaaAssistantArknights`
3. 创建或修改以下注册表项：
   - `OCRProvider` = `cpu` (字符串值)
   - `GPUEnabled` = `0` (DWORD值)

## 验证配置

配置完成后，重启MAA并检查日志。如果看到类似以下内容，则表示CPU模式已成功启用：

```
[I:onnxruntime:, inference_session.cc:1462 onnxruntime::InferenceSession::Initialize] Initializing session with CPUExecutionProvider
```

## 其他建议

1. **更新显卡驱动**：即使使用CPU模式，更新驱动也可能解决潜在的兼容性问题
2. **检查DirectX版本**：确保系统安装了DirectX 12（Windows 10 1709或更高版本）
3. **验证OCR模型**：确保 `assets/MaaCommonAssets/OCR/` 目录下的模型文件完整
4. **清理临时文件**：删除MAA的临时文件夹，避免缓存问题

## 常见问题排查

如果配置后仍然出现错误：

1. 检查配置文件路径是否正确
2. 确保配置文件格式为有效的JSON
3. 尝试重新安装MAA最新版本
4. 查看MAA日志文件获取更详细的错误信息

## MAAGC项目特定说明

由于MAAGC是基于MAA框架开发的插件项目，OCR配置由MAA主程序控制。您需要在MAA主程序中进行上述配置，而不是在MAAGC项目文件夹中。

如果您是通过MAAGC直接启动的MAA，请确保MAAGC正确传递了OCR配置参数。