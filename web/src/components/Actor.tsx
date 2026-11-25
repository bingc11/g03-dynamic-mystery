import React, { useState, useEffect, useCallback } from "react";
import {
  Actor,
  LLMMessage,
  useMysteryContext,
} from "../providers/mysteryContext";
import { Badge, Button, Group, Stack, Text, TextInput, ActionIcon, Tooltip } from "@mantine/core";
import { IconPhoto, IconRefresh, IconNotes, IconPaperclip } from "@tabler/icons-react";
import invokeAI, { invokeAIStream } from "../api/invoke";
import ActorImage from "./ActorImage";
import ChatMessage from "./ChatMessage";
import { generateBackgroundFromActor } from "../api/backgroundGenerator";
import { useSessionContext } from "../providers/sessionContext";
import { useScriptContext } from "../providers/scriptContext";
import { decisionLabel, useNpcActions } from "../providers/npcActions";
import CHARACTER_DATA from "../characters.json";
import { 
  generateRoleReactionPrompt, 
  generatePlayerSelfPrompt, 
  getInteractionMode,
  detectEvidencePresentation,
  generateEvidenceReactionPrompt,
  detectNoteSharing,
  generateNoteReactionPrompt
} from "../utils/roleInteraction";
import { generateNotesContext } from "../utils/noteManager";
import { loadEvidenceContext } from "../utils/evidenceManager";
import EvidenceSelectorPanel from "./evidence/EvidenceSelectorPanel";
import NoteSelectorPanel from "./notes/NoteSelectorPanel";
import { Evidence } from "../types/evidence";
import { Note } from "../types/notes";
import { getFullEvidenceForAI } from "../utils/evidenceManager";

interface Props {
  actor: Actor;
  currentPlayerActor?: Actor;
  postGame?: boolean;
}

const sendChat = async (
  messages: LLMMessage[],
  setActors: (update: (all: Record<number, Actor>) => Record<number, Actor>) => void,
  globalStory: string,
  sessionId: string,
  actor: Actor,
  setLoading: React.Dispatch<React.SetStateAction<boolean>>,
  currentPlayerActor?: Actor,
  detectiveName?: string,
  victimName?: string,
  allActors?: Record<number, Actor>
) => {
  setLoading(true);
  const setActor = (a: Partial<Actor>) => {
    setActors((all) => {
      const newActors = { ...all };
      newActors[actor.id] = {
        ...newActors[actor.id],
        ...a,
      };
      return newActors;
    });
  };

  setActor({ messages });

  // 智能角色交互逻辑
  let enhancedActor = { ...actor, messages };
  
  if (currentPlayerActor) {
    const mode = getInteractionMode(currentPlayerActor, actor);
    const lastMessage = messages[messages.length - 1];
    
    if (lastMessage && lastMessage.role === 'user') {
      let enhancedPrompt = '';
      
      if (mode === 'player_self') {
        // 玩家自我对话 - 思路梳理
        enhancedPrompt = generatePlayerSelfPrompt(actor, lastMessage.content);
      } else {
        // 其他角色对话 - 根据身份调整反应
        // 检测是否是笔记分享消息
        const noteDetection = detectNoteSharing(lastMessage.content);
        
        if (noteDetection.isNoteMessage && noteDetection.noteTitle && noteDetection.noteContent) {
          // 处理笔记分享
          enhancedPrompt = generateNoteReactionPrompt(
            currentPlayerActor, 
            actor, 
            noteDetection.noteTitle,
            noteDetection.noteContent,
            lastMessage.content
          );
        } else {
          // 常规对话处理
          // 不再自动加载笔记上下文，改为通过笔记选择器手动添加
          // 搭档角色现在需要玩家主动选择笔记进行分享，而不是自动获取所有笔记
          let notesContext = '';
          
          // 将玩家的身份信息注入：名字、个性、背景、当前目标
          const playerIntro = `【玩家身份】你将与一位调查者对话：\n- 名字：${currentPlayerActor.name}（玩家）\n- 个性：${currentPlayerActor.personality || '理性谨慎'}\n- 背景：${currentPlayerActor.bio || '暂无背景信息'}\n- 当前上下文：${currentPlayerActor.context || '正在调查本案'}\n`;
          enhancedPrompt = playerIntro + generateRoleReactionPrompt(currentPlayerActor, actor, lastMessage.content, allActors, notesContext);
        }
      }
      
      // 将增强的提示词添加到消息中
      enhancedActor = {
        ...actor,
        messages: [
          ...messages.slice(0, -1), // 除了最后一条用户消息
          {
            role: 'user' as const,
            content: enhancedPrompt
          }
        ]
      };
    }
  }

  const data = await invokeAI({
    globalStory,
    sessionId,
    characterFileVersion: CHARACTER_DATA.fileKey,
    actor: enhancedActor,
    detectiveName,
    victimName,
    allActors,
  });

  setActor({
    messages: [
      ...messages,
      {
        role: "assistant",
        content: data.final_response,
      },
    ],
  });
  setLoading(false);
};

const sendChatStream = (
  messages: LLMMessage[],
  setActors: (update: (all: Record<number, Actor>) => Record<number, Actor>) => void,
  globalStory: string,
  sessionId: string,
  actor: Actor,
  setLoading: React.Dispatch<React.SetStateAction<boolean>>,
  currentPlayerActor?: Actor,
  postGame?: boolean,
  detectiveName?: string,
  victimName?: string,
  allActors?: Record<number, Actor>,
  managedChat = false,
) => {
  setLoading(true);

  // 智能角色交互逻辑
  let enhancedActor = { ...actor, messages };
  
  // 在后剧情模式下，直接使用原始消息，不进行增强处理
  if (currentPlayerActor && !postGame && !managedChat) {
    const mode = getInteractionMode(currentPlayerActor, actor);
    const lastMessage = messages[messages.length - 1];
    
    if (lastMessage && lastMessage.role === 'user') {
      let enhancedPrompt = '';
      
      if (mode === 'player_self') {
        // 玩家自我对话 - 思路梳理
        enhancedPrompt = generatePlayerSelfPrompt(actor, lastMessage.content);
      } else {
        // 其他角色对话 - 根据身份调整反应
        // 检测是否为证物出示
        const evidenceDetection = detectEvidencePresentation(lastMessage.content);
        
        if (evidenceDetection.isEvidenceMessage && evidenceDetection.evidenceName) {
          // 证物出示情况 - 使用特殊的证物反应提示词
          const evidenceContext = loadEvidenceContext(sessionId);
          const evidence = evidenceContext.evidences.find(e => e.name === evidenceDetection.evidenceName);
          
          if (evidence) {
            enhancedPrompt = generateEvidenceReactionPrompt(currentPlayerActor, actor, evidence, lastMessage.content);
          } else {
            // 如果找不到证物，使用默认提示词
            enhancedPrompt = generateRoleReactionPrompt(currentPlayerActor, actor, lastMessage.content, allActors);
          }
        } else {
          // 正常对话 - 根据身份调整反应
          // 获取笔记上下文（仅对搭档角色）
          let notesContext = '';
          if (actor.isPartner || actor.isAssistant) {
            notesContext = generateNotesContext(sessionId);
            if (notesContext) {
            }
          }
          
          enhancedPrompt = generateRoleReactionPrompt(currentPlayerActor, actor, lastMessage.content, allActors, notesContext);
        }
      }
      
      // 将增强的提示词添加到消息中
      enhancedActor = {
        ...actor,
        messages: [
          ...messages.slice(0, -1), // 除了最后一条用户消息
          {
            role: 'user' as const,
            content: enhancedPrompt
          }
        ]
      };
    }
  }

  if (managedChat) {
    enhancedActor = {
      ...enhancedActor,
      isKiller: false,
      roleType: actor.roleType === '凶手' ? '嫌疑人' : actor.roleType,
      secret: '',
      violation: '',
      context: '以角色口吻回应日常话题。调查事实由调查系统提供。请保留未查证的说法，不补写案情、证据或角色已经执行的行动。',
      messages: messages.slice(-12).map(({ role, content }) => ({ role, content })),
    };
  }

  let assistantMessage: LLMMessage = { role: "assistant", content: "" };
  const placeholder = assistantMessage;
  setActors(all => {
    const current = all[actor.id];
    if (!current || current.name !== actor.name) return all;
    return {
      ...all,
      [actor.id]: { ...current, messages: [...current.messages, messages[messages.length - 1], placeholder] },
    };
  });

  const updateAssistant = (content: string) => {
    const previous = assistantMessage;
    const updated: LLMMessage = { role: "assistant", content };
    assistantMessage = updated;
    setActors(all => {
      const current = all[actor.id];
      if (!current?.messages.includes(previous)) return all;
      return {
        ...all,
        [actor.id]: { ...current, messages: current.messages.map(message => message === previous ? updated : message) },
      };
    });
  };

  const cancelStream = invokeAIStream({
    globalStory,
    sessionId,
    characterFileVersion: CHARACTER_DATA.fileKey,
    actor: enhancedActor,
    detectiveName,
    victimName,
    allActors: managedChat ? undefined : allActors,
    onChunk: (content: string) => updateAssistant(assistantMessage.content + content),
    onEnd: () => {
      setLoading(false);
    },
    onError: (error: string) => {
      console.error("❌ 流式响应错误:", error);
      setLoading(false);
      updateAssistant(`Error: ${error}`);
    },
  });

  return cancelStream;
};

function ReplyDetails({ message }: { message: LLMMessage }) {
  const npc = useNpcActions();
  const [shared, setShared] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [error, setError] = useState('');
  const label = decisionLabel(message.npcDriver);
  const classification = message.npcClassification === 'claim' || message.npcClassification === 'fact';
  const turnId = message.npcTurnId;
  if (message.role !== 'assistant' || !turnId || (!label && !classification && !message.npcSource)) return null;

  async function share() {
    if (!npc || !turnId || shared || sharing) return;
    setSharing(true);
    setError('');
    try {
      await npc.share(turnId);
      setShared(true);
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : '回报暂时无法公开');
    } finally {
      setSharing(false);
    }
  }

  return (
    <Group gap="xs" mb="sm" pl="sm">
      {label && <Badge size="xs" color={message.npcDriver === 'fallback' ? 'orange' : 'cyan'} variant="light">{label}</Badge>}
      {classification && <Badge size="xs" color={message.npcClassification === 'fact' ? 'teal' : 'yellow'} variant="light">
        {message.npcClassification === 'fact' ? '已核实材料' : '角色主张'}
      </Badge>}
      {message.npcSource && <Text size="xs" c="gray.3">来源 {message.npcSource}</Text>}
      {classification && npc?.managed && (
        <Button variant="subtle" color="cyan" size="compact-xs" loading={sharing} disabled={shared} onClick={() => void share()}>
          {shared ? '已公开' : '公开回报'}
        </Button>
      )}
      {error && <Text size="xs" c="red.3" role="alert">{error}</Text>}
    </Group>
  );
}

const ActorChat = ({ actor, currentPlayerActor, postGame }: Props) => {
  const [currMessage, setCurrMessage] = React.useState("");
  const { actors, setActors, globalStory } = useMysteryContext();
  const latestActors = React.useRef(actors);
  latestActors.current = actors;
  const { currentScript } = useScriptContext();
  const npcAction = useNpcActions();
  const [loading, setLoading] = useState(false);
  const [cancelStream, setCancelStream] = useState<(() => void) | null>(null);
  const [backgroundImage, setBackgroundImage] = useState<string | null>(null);
  const [isGeneratingBackground, setIsGeneratingBackground] = useState(false);
  // 聊天背景固定尺寸（与生成图一致）
  const [backgroundHeight, setBackgroundHeight] = useState<number>(1024);
  const [backgroundWidth, setBackgroundWidth] = useState<number>(1792);
  const containerRef = React.useRef<HTMLDivElement | null>(null);
  const sessionId = useSessionContext();
  
  // 证物和笔记发送相关状态
  const [showEvidenceSelector, setShowEvidenceSelector] = useState(false);
  const [showNoteSelector, setShowNoteSelector] = useState(false);
  
  // 移除不需要的缓存逻辑

  // 从当前脚本中获取侦探和受害者名称
  const detectiveName = currentScript?.characters?.find(char => char.isPlayer)?.name;
  const victimName = currentScript?.characters?.find(char => char.isVictim)?.name;

  const sendFromDialogue = async (message: LLMMessage, evidenceId?: string) => {
    setLoading(true);
    setCancelStream(null);
    const outcome = !postGame && npcAction
      ? await npcAction.dispatch(actor, message.content, evidenceId)
      : 'legacy';
    const current = latestActors.current[actor.id];
    if (outcome === 'handled' || current?.name !== actor.name) {
      setLoading(false);
      return;
    }
    const cancel = sendChatStream(
      [...current.messages, message], setActors, globalStory, sessionId, current, setLoading,
      currentPlayerActor, postGame, detectiveName, victimName, latestActors.current, outcome === 'chat',
    );
    setCancelStream(() => cancel);
  };

  const handleSendMessage = () => {
    const text = currMessage.trim();
    if (!text || loading) return;
    setCurrMessage("");
    void sendFromDialogue({ role: "user", content: text });
  };

  const handleStopGeneration = () => {
    if (cancelStream) {
      cancelStream();
      setCancelStream(null);
      setLoading(false);
    }
  };

  const handleKeyPress = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSendMessage();
    }
  };

  // 处理证物发送
  const handleEvidenceSend = (evidence: Evidence, textContent?: string) => {
    if (loading) return;
    // 构建完整的证物信息消息，供AI生成智能反应
    // AI获取完整信息（包含概况和线索）
    let evidenceDetails = getFullEvidenceForAI(evidence);
    
    // 如果有详细分析（已解锁），添加到AI上下文中
    if (evidence.detailedDescription && evidence.unlockLevel >= 2) {
      evidenceDetails += `\n详细分析：${evidence.detailedDescription}`;
    }
    
    // 如果有深度发现（已解锁），添加到AI上下文中
    if (evidence.deepDescription && evidence.unlockLevel >= 3) {
      evidenceDetails += `\n深度发现：${evidence.deepDescription}`;
    }
    
    // 添加重要程度和相关角色信息
    const importanceMap = {
      critical: '决定性',
      high: '关键',
      medium: '重要',
      low: '一般'
    };
    evidenceDetails += `\n重要程度：${importanceMap[evidence.importance as keyof typeof importanceMap]}`;
    
    if (evidence.relatedActors && evidence.relatedActors.length > 0) {
      evidenceDetails += `\n相关角色：${evidence.relatedActors.join('、')}`;
    }

    const evidenceMessage: LLMMessage = {
      role: "user",
      content: `[发送证物] ${evidence.name}: ${evidenceDetails}${textContent ? `\n\n${textContent}` : ''}`
    };

    // 立即关闭证物选择器，提供即时反馈
    setShowEvidenceSelector(false);

    void sendFromDialogue(evidenceMessage, evidence.id);
  };

  // 处理笔记发送
  const handleNoteSend = (note: Note, textContent?: string) => {
    const noteMessage: LLMMessage = {
      role: "user", 
      content: `[分享笔记] ${note.title}: ${note.content}${textContent ? `\n\n${textContent}` : ''}`
    };

    // 立即关闭笔记选择器，提供即时反馈
    setShowNoteSelector(false);

    const cancel = sendChatStream([...actor.messages, noteMessage], setActors, globalStory, sessionId, actor, setLoading, currentPlayerActor, postGame, detectiveName, victimName, actors, npcAction?.managed);
    setCancelStream(() => cancel);
  };

  // 生成背景图片
  const handleGenerateBackground = useCallback(async () => {
    if (isGeneratingBackground) return;
    
    setIsGeneratingBackground(true);
    try {
      const result = await generateBackgroundFromActor(actor);
      
      if (result.success && result.background_path) {
        setBackgroundImage(result.background_path);
      } else {
        console.warn('⚠️ 背景生成失败:', result.message);
      }
    } catch (error) {
      console.error('❌ 背景生成异常:', error);
    } finally {
      setIsGeneratingBackground(false);
    }
  }, [actor, isGeneratingBackground]);

  // 背景图片尺寸：默认按90%缩放；若容器更窄，则继续等比缩小，始终完整显示
  const calculateBackgroundDimensions = (imagePath: string | null) => {
    if (!imagePath) return { width: 600, height: 200 };
    const originalWidth = 1792;
    const originalHeight = 1024;
    // 目标优先缩小60%
    const preferredWidth = Math.round(originalWidth * 0.6); // 1075
    // 估算容器可用宽度（避免横向滚动）。若获取不到，退化为视口的72%
    const hostWidth = containerRef.current?.clientWidth ?? Math.floor(window.innerWidth * 0.72);
    // 由于内容区有内边距，预留一些空间
    const safeWidth = Math.max(320, hostWidth - 32);
    const finalWidth = Math.min(preferredWidth, safeWidth);
    const scale = finalWidth / originalWidth;
    const finalHeight = Math.round(originalHeight * scale);
    return { width: finalWidth, height: finalHeight };
  };

  // 组件加载时设置背景图片 - 只显示已有的，不自动生成
  useEffect(() => {
    // 🔍 调试：输出角色背景图片加载信息
    // console.log(`🎨 Actor组件 - 角色 ${actor.name} 背景图片加载:`, {
    //   actorBackgroundImage: actor.backgroundImage,
    //   currentBackgroundImage: backgroundImage,
    //   actorId: actor.id
    // });
    
    // 只检查角色是否已有预设的背景图片，有就显示，没有就清空
    if (actor.backgroundImage) {
      // console.log(`✅ 设置角色 ${actor.name} 的背景图片:`, actor.backgroundImage);
      setBackgroundImage(actor.backgroundImage);
      const dimensions = calculateBackgroundDimensions(actor.backgroundImage);
      // console.log(`📐 计算背景图片尺寸:`, dimensions);
      setBackgroundWidth(dimensions.width);
      setBackgroundHeight(dimensions.height);
    } else {
      // console.log(`❌ 角色 ${actor.name} 没有背景图片`);
      // 没有预设背景图片，清空背景，不自动生成
      setBackgroundImage(null);
      setBackgroundWidth(600);
      setBackgroundHeight(200);
    }
  }, [actor.backgroundImage, actor.name, actor.id]); // 添加更多依赖以便调试

  // 监听窗口尺寸变化，动态调整容器大小，避免出现横向滚动条
  useEffect(() => {
    const onResize = () => {
      if (backgroundImage) {
        const dimensions = calculateBackgroundDimensions(backgroundImage);
        setBackgroundWidth(dimensions.width);
        setBackgroundHeight(dimensions.height);
      }
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [backgroundImage]);

  return (
    <div
      ref={containerRef}
      style={{
        position: 'relative',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center', // 水平居中
        justifyContent: 'flex-start',
        padding: '16px'
      }}
    >
      {/* 内容层 */}
      <Stack
        className="mystery-card"
        style={{
          position: 'relative',
          zIndex: 1,
          padding: 16,
          width: '100%',
          background: "linear-gradient(135deg, #1A1A2E 0%, #1E1E1E 100%)",
          overflow: 'visible' // 允许内部内容完整显示
        }}
      >
      {/* 紧凑的角色头像和信息区域 - 极光动画 */}
      <div 
        className="character-info-aurora"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          padding: '12px 16px',
          borderRadius: '8px',
          border: '1px solid rgba(0, 194, 255, 0.2)',
          marginBottom: '16px',
          position: 'relative',
          overflow: 'hidden'
        }}
      >
        <div style={{ flexShrink: 0 }}>
          <ActorImage actor={actor} />
        </div>
        <div style={{ flex: 1 }}>
          <Group justify="space-between" align="center">
            <Text
              className="mystery-title"
              style={{
                fontWeight: "bold",
                fontSize: "18px",
                marginBottom: "4px",
                color: "#FFFFFF",
                textShadow: "0 2px 4px rgba(0, 0, 0, 0.8)"
              }}
            >
              {actor.name}
            </Text>
            
            {/* 背景生成按钮 */}
            <Group gap="xs">
              <Tooltip label="生成聊天背景">
                <ActionIcon
                  size="sm"
                  variant="subtle"
                  color="cyan"
                  loading={isGeneratingBackground}
                  onClick={handleGenerateBackground}
                  style={{
                    backgroundColor: 'rgba(0, 194, 255, 0.1)',
                    '&:hover': {
                      backgroundColor: 'rgba(0, 194, 255, 0.2)'
                    }
                  }}
                >
                  <IconPhoto size={16} />
                </ActionIcon>
              </Tooltip>
              
              {backgroundImage && (
                <Tooltip label="重新生成背景">
                  <ActionIcon
                    size="sm"
                    variant="subtle"
                    color="orange"
                    loading={isGeneratingBackground}
                    onClick={handleGenerateBackground}
                    style={{
                      backgroundColor: 'rgba(255, 183, 77, 0.1)',
                      '&:hover': {
                        backgroundColor: 'rgba(255, 183, 77, 0.2)'
                      }
                    }}
                  >
                    <IconRefresh size={16} />
                  </ActionIcon>
                </Tooltip>
              )}
            </Group>
          </Group>
          
          <div 
            className="mystery-subtitle"
            style={{ 
              fontSize: "13px",
              lineHeight: "1.4",
              color: "#B8B8B8",
              textShadow: "0 1px 2px rgba(0, 0, 0, 0.8)"
            }}
          >
            {actor.bio}
          </div>
        </div>
      </div>

      {/* 极光分隔线 */}
      <div 
        className="character-separator-aurora"
        style={{
          position: 'relative',
          width: '100%',
          height: '3px',
          marginBottom: '20px',
          borderRadius: '2px'
        }}
      />

      {/* 对话消息区域 - 带背景图片 */}
      <div
        style={{
          position: 'relative',
          padding: '16px',
          borderRadius: '12px',
          background: backgroundImage 
            ? `url(/${backgroundImage})` 
            : 'transparent',
          backgroundSize: '100% 100%', // 容器与图片同尺寸，完整显示
          backgroundPosition: 'center',
          backgroundRepeat: 'no-repeat',
          height: backgroundImage ? `${backgroundHeight}px` : 'auto', // 🔧 使用固定高度匹配背景图片
          width: backgroundImage ? `${backgroundWidth}px` : '100%', // 🔧 使用固定宽度匹配背景图片
          display: 'flex',
          flexDirection: 'column'
        }}
        title={`背景图片: ${backgroundImage || '无'}`} // 🔍 调试：鼠标悬停显示背景图片路径
      >
        {/* 背景遮罩层 */}
        {backgroundImage && (
          <div
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              backgroundColor: 'rgba(26, 26, 46, 0.75)',
              borderRadius: '12px',
              zIndex: 0
            }}
          />
        )}
        
        {/* 对话消息内容 */}
        <div style={{ 
          position: 'relative', 
          zIndex: 1, 
          flex: 1,
          overflowY: 'auto',
          paddingRight: '8px' // 为滚动条留出空间
        }}>
          {actor.messages.map((m, i) => (
            <React.Fragment key={m.npcTurnId ? m.npcTurnId + ':' + m.role : i}>
              <ChatMessage message={m} actor={actor} currentPlayerActor={currentPlayerActor} isUser={m.role === "user"} />
              <ReplyDetails message={m} />
            </React.Fragment>
          ))}
        </div>
        
        {/* 输入框区域 - 固定在底部 */}
        {postGame && npcAction?.managed ? (
          <Text size="sm" c="gray.3" mt="md">此席位已结案。可在调查记录中查看解释。</Text>
        ) : <Group style={{
          marginTop: '16px',
          flexShrink: 0 // 防止输入框被压缩
        }}>
        {loading ? (
          <>
            <TextInput
              className="mystery-input"
              placeholder="正在沟通中..."
              disabled={true}
              style={{ 
                flexGrow: 1,
                background: 'rgba(60, 60, 60, 0.5)',
                border: '2px solid rgba(189, 189, 189, 0.3)',
                color: '#BDBDBD',
                fontSize: '16px',
                padding: '12px 16px',
                borderRadius: '8px',
                backdropFilter: 'blur(5px)',
                '&::placeholder': {
                  color: '#BDBDBD',
                  opacity: 0.8
                }
              }}
            />
            <div className="loading-cyber" />
            {cancelStream && <Button
              size="sm" 
              variant="outline" 
              className="btn-crimson"
              onClick={handleStopGeneration}
              style={{ 
                borderColor: '#E63946',
                color: '#E63946',
                backgroundColor: 'rgba(230, 57, 70, 0.1)'
              }}
            >
              停止
            </Button>}
          </>
        ) : (
          <TextInput
            className="mystery-input"
            placeholder={`与${actor.name}对话`}
            onChange={(event) => {
              setCurrMessage(event.currentTarget.value);
            }}
            value={currMessage}
            style={{ 
              flexGrow: 1,
              background: 'rgba(30, 30, 30, 0.9)',
              border: '2px solid #00C2FF',
              color: '#FFFFFF',
              fontSize: '16px',
              padding: '12px 16px',
              borderRadius: '8px',
              backdropFilter: 'blur(5px)',
              '&::placeholder': {
                color: '#B8B8B8',
                fontSize: '16px'
              }
            }}
            onKeyPress={handleKeyPress}
            styles={{
              input: {
                '&::placeholder': {
                  color: '#B8B8B8 !important',
                  fontSize: '16px',
                  opacity: 1
                }
              }
            }}
          />
        )}

        <Tooltip label="发送证物">
          <ActionIcon
            aria-label="发送证物"
            size="lg"
            variant="subtle"
            color="yellow"
            onClick={() => setShowEvidenceSelector(true)}
            disabled={loading}
            style={{
              backgroundColor: 'rgba(255, 255, 0, 0.1)',
              '&:hover': {
                backgroundColor: 'rgba(255, 255, 0, 0.2)'
              }
            }}
          >
            <IconPaperclip size={20} />
          </ActionIcon>
        </Tooltip>

        <Tooltip label="发送笔记">
          <ActionIcon
            size="lg"
            variant="subtle"
            color="purple"
            onClick={() => setShowNoteSelector(true)}
            disabled={loading}
            style={{
              backgroundColor: 'rgba(128, 0, 128, 0.1)',
              '&:hover': {
                backgroundColor: 'rgba(128, 0, 128, 0.2)'
              }
            }}
          >
            <IconNotes size={20} />
          </ActionIcon>
        </Tooltip>

        <Button 
          disabled={loading || !currMessage.trim()} 
          onClick={handleSendMessage}
          style={{ 
            background: (loading || !currMessage.trim()) ? 'rgba(189, 189, 189, 0.3)' : '#00C2FF',
            border: (loading || !currMessage.trim()) ? '2px solid rgba(189, 189, 189, 0.5)' : '2px solid #00C2FF',
            color: (loading || !currMessage.trim()) ? '#BDBDBD' : '#FFFFFF',
            fontWeight: '700',
            textShadow: (loading || !currMessage.trim()) ? 'none' : '0 1px 2px rgba(0, 0, 0, 0.8)',
            filter: (loading || !currMessage.trim()) ? 'grayscale(0.8)' : 'contrast(1.1)',
            cursor: (loading || !currMessage.trim()) ? 'not-allowed' : 'pointer',
            opacity: (loading || !currMessage.trim()) ? 0.6 : 1
          }}
        >
          {loading ? '发送中...' : '发送'}
        </Button>
        </Group>}
      </div>

      </Stack>

      {/* 证物选择器 */}
      <EvidenceSelectorPanel
        opened={showEvidenceSelector}
        onClose={() => setShowEvidenceSelector(false)}
        onSelect={() => {}} // 可选的选择回调
        onSend={handleEvidenceSend}
        sessionId={sessionId}
        currentActor={actor.name}
        inventory={npcAction?.inventory}
      />

      {/* 笔记选择器 */}
      <NoteSelectorPanel
        opened={showNoteSelector}
        onClose={() => setShowNoteSelector(false)}
        onSelect={() => {}} // 可选的选择回调
        onSend={handleNoteSend}
        sessionId={sessionId}
        currentActor={actor.name}
      />
    </div>
  );
};

export { sendChat, sendChatStream };
export default ActorChat;
