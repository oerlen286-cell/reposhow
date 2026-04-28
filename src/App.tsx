import React, { useState, useEffect } from 'react';
import { Player } from '@remotion/player';
import { GithubIntro } from './GithubIntro';
import axios from 'axios';
import { demoPreviewVideoProps } from './demoPreview';

const FPS = 30;
const SCENE1 = 4 * FPS;
const SCENE2 = 4 * FPS;

export default function App() {
    const [url, setUrl] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [serverLogs, setServerLogs] = useState('');

    useEffect(() => {
        if (!loading) return;
        const interval = setInterval(async () => {
            try {
                const res = await axios.get('/out/status.log?t=' + Date.now());
                if (typeof res.data === 'string') {
                    setServerLogs(res.data);
                }
            } catch (e) { }
        }, 800);
        return () => clearInterval(interval);
    }, [loading]);

    // The dynamically changing metadata and props
    const [videoProps, setVideoProps] = useState(demoPreviewVideoProps);

    const handleGenerate = async () => {
        if (!url) return;
        setLoading(true);
        setError('');
        try {
            // Calls the Python backend to do OCR/Playwright screenshots and return JSON logic
            const res = await axios.post('/api/generate', {
                url,
                lang: videoProps.lang,
                scrollDistance: Number(videoProps.scrollDistance),
                scrollDuration: Number(videoProps.scrollDurationSec)
            });
            setVideoProps({
                ...videoProps,
                ...res.data.props,
                scrollSubtitle: res.data.narrationScript || res.data.props.scrollSubtitle
            });
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Failed to generate video data');
        } finally {
            setLoading(false);
        }
    };

    const triggerMp4Download = (href: string, filename: string) => {
        const path = href.split("?")[0];
        const a = document.createElement("a");
        a.href = path;
        a.download = filename.endsWith(".mp4") ? filename : `${filename}.mp4`;
        a.rel = "noopener";
        a.style.display = "none";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    };

    const handleExport = async () => {
        if (!url) {
            alert("请输入 GitHub URL！");
            return;
        }
        setLoading(true);
        setError('');
        try {
            const slug = url.split('/').filter(Boolean).pop()?.toLowerCase() || 'video';
            const res = await axios.post('/api/export', {
                slug,
                props: videoProps
            });
            if (res.data.success) {
                const videoUrl = res.data.videoUrl as string;
                triggerMp4Download(videoUrl, slug);
                alert("渲染成功，已开始下载 MP4（若未出现保存框，请检查浏览器下载权限或弹窗拦截）。");
            }
        } catch (err: any) {
            setError(err.response?.data?.detail || '渲染失败');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="app-container">
            <header className="navbar">
                <h1>🎬 Reposhow Web UI</h1>
            </header>

            <main className="main-content">
                <aside className="sidebar">
                    <h2>Edit Video</h2>
                    <div className="form-group">
                        <label>GitHub URL</label>
                        <input
                            type="text"
                            placeholder="https://github.com/facebook/react"
                            value={url}
                            onChange={e => setUrl(e.target.value)}
                        />
                    </div>
                    <button className="btn btn-primary" onClick={handleGenerate} disabled={loading}>
                        {loading ? 'Processing...' : 'Load & Parse Repo'}
                    </button>

                    {loading && (
                        <div className="log-viewer">
                            <pre>{serverLogs || "Waiting for Python Playwright & LLM logs..."}</pre>
                        </div>
                    )}

                    {error && <p className="error">{error}</p>}

                    <div className="form-group">
                        <label>Language</label>
                        <select
                            value={videoProps.lang}
                            onChange={e => setVideoProps({ ...videoProps, lang: e.target.value })}
                        >
                            <option value="zh">Chinese</option>
                            <option value="en">English</option>
                        </select>
                    </div>

                    <div className="form-group">
                        <label>Transition Style</label>
                        <select
                            value={videoProps.transitionStyle}
                            onChange={e => setVideoProps({ ...videoProps, transitionStyle: e.target.value })}
                        >
                            <option value="none">None</option>
                            <option value="black">Fade Black</option>
                            <option value="white">Fade White</option>
                            <option value="chromatic">Chromatic Aberration</option>
                            <option value="blur">Blur</option>
                            <option value="zoom">Zoom</option>
                            <option value="dissolve">Dissolve</option>
                            <option value="slide">Slide</option>
                        </select>
                    </div>
                    <div className="form-group">
                        <label>Narration / Subtitle</label>
                        <textarea
                            value={videoProps.scrollSubtitle}
                            onChange={e => setVideoProps({ ...videoProps, scrollSubtitle: e.target.value })}
                        />
                    </div>


                    <div className="form-group">
                        <label>BGM Path</label>
                        <input
                            type="text"
                            value={videoProps.bgMusic}
                            onChange={e => setVideoProps({ ...videoProps, bgMusic: e.target.value })}
                        />
                    </div>

                    <button className="btn btn-success" onClick={handleExport} disabled={loading}>
                        Export MP4
                    </button>
                </aside>

                <section className="preview-pane">
                    <div className="player-wrapper">
                        <Player
                            component={GithubIntro}
                            inputProps={videoProps}
                            durationInFrames={SCENE1 + SCENE2 + (Number(videoProps.scrollDurationSec) || 25) * FPS}
                            fps={FPS}
                            compositionWidth={1920}
                            compositionHeight={1080}
                            style={{
                                width: '100%',
                                aspectRatio: '16/9',
                                borderRadius: '8px',
                                boxShadow: '0 4px 12px rgba(0,0,0,0.1)'
                            }}
                            controls
                            autoPlay={false}
                            loop
                        />
                    </div>
                </section>
            </main>
        </div>
    );
}
