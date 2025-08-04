# Plex 歌单导入工具

## 简介

这是一个图形界面的工具，旨在帮助用户将网易云音乐或QQ音乐的在线歌单轻松导入到自己的 Plex 媒体服务器中。

## 依赖安装

在运行此工具之前，请确保您已经安装了所有必需的 Python 库。您可以使用以下命令进行安装：

```bash
pip install requests plexapi
```

## 配置说明

为了让工具能够连接到您的 Plex 服务器，您需要创建一个名为 `plex_config.json` 的配置文件。该文件应与主程序 `playlist_importer.py` 放置在同一目录下。

文件内容如下所示：

```json
{
  "plex_url": "http://your_plex_server_ip:32400",
  "plex_token": "your_plex_token"
}
```

请将 `your_plex_server_ip` 替换为您的 Plex 服务器的实际地址，并将 `your_plex_token` 替换为您的 Plex API Token。

## 使用方法

配置完成后，您可以直接运行主程序来启动工具：

```bash
python playlist_importer.py
```

程序启动后，您将看到一个图形界面，按照界面提示操作即可导入歌单。