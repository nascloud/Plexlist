document.addEventListener('DOMContentLoaded', () => {
    // DOM 元素获取
    const plexConfigForm = document.getElementById('plex-config-form');
    const extractForm = document.getElementById('extract-form');
    const importToPlexButton = document.getElementById('import-to-plex');
    const songList = document.getElementById('song-list');
    const resultsContainer = document.getElementById('results-container');
    const statusContainer = document.getElementById('status-container');
    const loader = document.getElementById('loader');
    const progressBar = document.getElementById('import-progress-bar');
    const statusMessage = document.getElementById('import-status-message');
    const progressText = document.getElementById('import-progress-text');

    // 全局变量
    let currentSongs = [];
    let taskId = null;
    let pollingInterval = null;

    /**
     * 从API错误响应中解析详细的错误信息
     * @param {object} errorData - 从 response.json() 解析的对象
     * @returns {string} - 格式化后的错误信息
     */
    function getErrorMessage(errorData) {
        if (!errorData || !errorData.detail) {
            return '未知错误';
        }
        const detail = errorData.detail;
        if (typeof detail === 'string') {
            return detail;
        }
        if (Array.isArray(detail)) {
            // 处理 FastAPI 验证错误, e.g. [{loc: ['body', 'url'], msg: 'field required', ...}]
            return detail.map(err => `${err.loc.slice(1).join('.')} - ${err.msg}`).join('; ');
        }
        if (typeof detail === 'object') {
            return JSON.stringify(detail);
        }
        return '未知错误格式';
    }

    // --- 1. Plex 配置模块 ---

    /**
     * 从服务器获取Plex配置并填充表单
     */
    async function getPlexConfig() {
        try {
            const response = await fetch('/api/v1/config/plex');
            if (response.ok) {
                const config = await response.json();
                document.getElementById('plex-url').value = config.plex_url || '';
                document.getElementById('plex-token').value = config.plex_token || '';
                document.getElementById('playlist-name').value = config.playlist_name || 'Plexlist';
                document.getElementById('import-mode').value = config.import_mode || 'append';
            } else {
                console.error('获取Plex配置失败');
            }
        } catch (error) {
            console.error('请求Plex配置时出错:', error);
        }
    }

    /**
     * 处理Plex配置表单的提交
     */
    plexConfigForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const formData = new FormData(plexConfigForm);
        const data = Object.fromEntries(formData.entries());

        try {
            const response = await fetch('/api/v1/config/plex', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
            });
            if (response.ok) {
                alert('配置已保存！');
            } else {
                const errorData = await response.json();
                alert(`保存失败: ${getErrorMessage(errorData)}`);
            }
        } catch (error) {
            console.error('保存配置时出错:', error);
            alert('保存配置时发生网络错误。');
        }
    });

    // --- 2. 歌单提取模块 ---
    extractForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        loader.style.display = 'inline-block';
        resultsContainer.style.display = 'none';
        statusContainer.style.display = 'none';
        statusMessage.textContent = '';
        songList.innerHTML = '';
        currentSongs = [];
        if (pollingInterval) clearInterval(pollingInterval);

        const formData = new FormData(extractForm);
        const data = {
            source: formData.get('platform'),
            url_or_id: formData.get('playlist_url'),
        };

        try {
            const response = await fetch('/api/v1/playlist/extract', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
            });

            if (response.ok) {
                const result = await response.json();
                currentSongs = result.songs;
                displaySongs(result.songs);
            } else {
                const errorData = await response.json();
                alert(`提取失败: ${getErrorMessage(errorData)}`);
            }
        } catch (error) {
            console.error('提取歌单时出错:', error);
            alert('提取歌单时发生网络错误。');
        } finally {
            loader.style.display = 'none';
        }
    });

    // --- 3. 结果显示模块 ---
    function displaySongs(songs) {
        songList.innerHTML = '';
        if (songs && songs.length > 0) {
            songs.forEach(song => {
                const li = document.createElement('li');
                li.textContent = `${song.title} - ${song.artist}`;
                songList.appendChild(li);
            });
            resultsContainer.style.display = 'block';
            importToPlexButton.style.display = 'block';
        } else {
            resultsContainer.style.display = 'none';
            importToPlexButton.style.display = 'none';
        }
    }

    // --- 4. 导入与状态模块 ---
    importToPlexButton.addEventListener('click', async () => {
        // 从表单中收集所需的值
        const playlistUrl = document.getElementById('playlist-url').value;
        const plexUrl = document.getElementById('plex-url').value;
        const plexToken = document.getElementById('plex-token').value;
        const plexPlaylistName = document.getElementById('playlist-name').value;
        let importMode = document.getElementById('import-mode').value;
        // 确保导入模式有效
        if (!["create_new", "update_existing"].includes(importMode)) {
            alert("请选择有效的导入模式(创建新列表或更新现有列表)");
            return;
        }

        // 构造符合后端 API 规范的扁平结构
        const data = {
            playlist_url: playlistUrl,
            plex_url: plexUrl,
            plex_token: plexToken,
            plex_playlist_name: plexPlaylistName,
            import_mode: importMode,
        };

        try {
            // UI 初始化
            statusContainer.style.display = 'block';
            progressBar.style.display = 'block';
            progressBar.value = 0;
            statusMessage.textContent = '正在开始导入任务...';
            progressText.textContent = '0%';
            if (pollingInterval) clearInterval(pollingInterval);

            const response = await fetch('/api/v1/import', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
            });

            if (response.ok) {
                const result = await response.json();
                taskId = result.task_id;
                statusMessage.textContent = '任务已启动，正在等待首次状态更新...';
                startPolling(taskId);
            } else {
                const errorData = await response.json();
                statusMessage.textContent = `创建导入任务失败: ${getErrorMessage(errorData)}`;
                progressBar.style.display = 'none';
            }
        } catch (error) {
            console.error('导入Plex时出错:', error);
            alert('导入Plex时发生网络错误。');
        }
    });

    function startPolling(id) {
        if (pollingInterval) clearInterval(pollingInterval);
        pollingInterval = setInterval(() => checkTaskStatus(id), 2000);
    }

    async function checkTaskStatus(id) {
        try {
            const response = await fetch(`/api/v1/import/status/${id}`);
            if (!response.ok) {
                console.error(`状态检查失败: HTTP ${response.status}`, await response.text());
                statusMessage.textContent = `检查状态失败 (HTTP ${response.status})。`;
                progressBar.style.display = 'none';
                clearInterval(pollingInterval);
                return;
            }

            try {
                const statusData = await response.json();
                if (!statusData || !statusData.status) {
                    throw new Error('无效的状态响应格式');
                }

                const { status, processed, total, message } = statusData;

                // 更新状态消息
                statusMessage.textContent = message || '状态更新中...';

                // 更新进度条和百分比
                if (total > 0 && processed != null) {
                    const percentage = Math.round((processed / total) * 100);
                    progressBar.value = percentage;
                    progressText.textContent = `${percentage}% (${processed}/${total})`;
                } else {
                    progressText.textContent = '...';
                }

                // 检查任务是否完成或失败
                if (status === 'completed' || status === 'failed') {
                    clearInterval(pollingInterval);
                    if (status === 'completed') {
                        progressBar.value = 100;
                        progressText.textContent = `100% (${total}/${total})`;
                        statusMessage.textContent = "导入成功完成！";
                    } else { // failed
                        statusMessage.textContent = `导入失败: ${message || '未知原因'}`;
                        progressBar.style.backgroundColor = '#ff0000';
                    }
                }
            } catch (parseError) {
                console.error('解析状态响应失败:', parseError);
                statusMessage.textContent = '解析状态响应时出错。';
                clearInterval(pollingInterval);
            }
        } catch (error) {
            console.error('轮询任务状态时出错:', error);
            statusMessage.textContent = `轮询时发生错误: ${error.message || '未知网络错误'}`;
            clearInterval(pollingInterval);
        }
    }

    // 初始化页面
    getPlexConfig();
});