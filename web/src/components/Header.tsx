import React from 'react';
import { Group, Image, Text, Anchor, Button } from '@mantine/core';
import { useNavigate, useLocation } from 'react-router-dom';
// 使用 Mantine 内置图标
import styles from './Header.module.css';  // Import the CSS module
import { useScriptContext } from '../providers/scriptContext';

export default function Header() {
  const navigate = useNavigate();
  const location = useLocation();
  const { currentScript } = useScriptContext();

  const isActive = (path: string) => location.pathname === path;
  
  // 获取当前显示的标题
  const getCurrentTitle = () => {
    // 在游戏页面或剧本播放页面显示当前剧本名称
    if (currentScript && (location.pathname === '/' || location.pathname.startsWith('/play/'))) {
      return currentScript.title;
    }
    // 在其他页面显示默认标题
    return 'AI 不在场证明';
  };

  return (
    <div 
      className={`${styles.header} particle-bg aurora-header`}
      style={{
        position: 'relative'
      }}
    >
      <div 
        className={styles['logo-container']}
        style={{
          cursor: 'default',
          userSelect: 'none'
        }}
      >
        <img 
          src={process.env.PUBLIC_URL + '/favicon.svg'}
          alt="AI 不在场证明 Logo"
          width="90px" 
          className={styles.logo}
          style={{
            filter: 'drop-shadow(0 0 10px rgba(0, 194, 255, 0.5))',
            cursor: 'default'
          }}
        />
        <div>
          <Text 
            size="lg" 
            className="aurora-title"
            style={{
              fontSize: '24px',
              cursor: 'default'
            }}
          >
            {getCurrentTitle()}
          </Text>
          <Text 
            size="12px"
            className="aurora-text-secondary"
            style={{
              fontSize: '14px',
              cursor: 'default'
            }}
          >
            多智能体大语言模型谋杀悬疑 |{' '}
            <a 
            href="https://github.com/ironman5366/ai-murder-mystery-hackathon"
              style={{
                color: '#4ECCA3',
                textDecoration: 'none',
                transition: 'all 0.3s ease'
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.color = '#00C2FF';
                e.currentTarget.style.textShadow = '0 0 5px rgba(0, 194, 255, 0.5)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.color = '#4ECCA3';
                e.currentTarget.style.textShadow = 'none';
              }}
            >
              破案剧本杀
            </a>
          </Text>
        </div>
      </div>
      
      {/* 导航按钮 */}
      <Group gap="sm" style={{ flex: 1, justifyContent: 'center' }}>
        <Button
          variant={isActive('/') ? 'filled' : 'subtle'}
          onClick={() => navigate('/')}
          size="sm"
          className={isActive('/') ? 'aurora-button-primary' : ''}
          style={{
            background: isActive('/') ? undefined : 'transparent',
            color: isActive('/') ? undefined : '#FFFFFF',
            border: isActive('/') ? undefined : '1px solid #00C2FF'
          }}
        >
          🎮 游戏
        </Button>
        <Button
          variant={isActive('/library') ? 'filled' : 'subtle'}
          onClick={() => navigate('/library')}
          size="sm"
          className={isActive('/library') ? 'aurora-button-primary' : ''}
          style={{
            background: isActive('/library') ? undefined : 'transparent',
            color: isActive('/library') ? undefined : '#FFFFFF',
            border: isActive('/library') ? undefined : '1px solid #00C2FF'
          }}
        >
          📚 剧本库
        </Button>
        <Button
          variant={isActive('/editor') ? 'filled' : 'subtle'}
          onClick={() => navigate('/editor')}
          size="sm"
          className={isActive('/editor') ? 'aurora-button-primary' : ''}
          style={{
            background: isActive('/editor') ? undefined : 'transparent',
            color: isActive('/editor') ? undefined : '#FFFFFF',
            border: isActive('/editor') ? undefined : '1px solid #00C2FF'
          }}
        >
          ✏️ 手动创建剧本
        </Button>
        <Button
          variant={isActive('/ai-generator') ? 'filled' : 'subtle'}
          onClick={() => navigate('/ai-generator')}
          size="sm"
          className={isActive('/ai-generator') ? 'aurora-button-danger' : ''}
          style={{
            background: isActive('/ai-generator') ? undefined : 'transparent',
            color: isActive('/ai-generator') ? undefined : '#FFFFFF',
            border: isActive('/ai-generator') ? undefined : '1px solid #E63946'
          }}
        >
          🤖 AI生成剧本
        </Button>
      </Group>

      <div className={styles.logos}>
        <Anchor 
          href="https://www.synthlabs.ai/" 
          target="_blank"
          className="hover-glow"
          style={{
            borderRadius: '8px',
            padding: '4px',
            transition: 'all 0.3s ease'
          }}
        >
          <Text size="sm">SynthLabs</Text>
        </Anchor>
        <Anchor 
          href="https://medarc.ai/" 
          target="_blank"
          className="hover-glow"
          style={{
            borderRadius: '8px',
            padding: '4px',
            transition: 'all 0.3s ease'
          }}
        >
          <Text size="sm">MedARC</Text>
        </Anchor>
      </div>
    </div>
  );
}
