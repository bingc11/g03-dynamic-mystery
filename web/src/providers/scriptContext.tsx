import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { Script, ScriptContextType, createNewScriptTemplate, getExampleScripts } from '../types/script';
import { 
  getCurrentScriptId, 
  setCurrentScriptId,
  findScriptById,
  deleteScriptFile 
} from '../utils/scriptManager';
import { 
  saveScriptToDB, 
  // getScriptsFromDB, 
  // getScriptFromDB, 
  deleteScriptFromDB,
  // migrateDataToDB 
} from '../api/database';
import { 
  markScriptAsDeleted, 
  filterDeletedScripts 
} from '../utils/storageManager';

const ScriptContext = createContext<ScriptContextType | undefined>(undefined);

interface ScriptProviderProps {
  children: ReactNode;
}

export const ScriptProvider: React.FC<ScriptProviderProps> = ({ children }) => {
  const [scripts, setScripts] = useState<Script[]>([]);
  const [currentScript, setCurrentScript] = useState<Script | null>(null);

  // 初始化时加载剧本数据
  useEffect(() => {
    const initializeScripts = async () => {
      try {
        // console.log('🚀 开始初始化剧本数据...');
        
        // 启用数据库功能，从数据库加载剧本数据
        
        // 首先尝试从数据库加载剧本
        let dbScripts: Script[] = [];
        try {
          const { getScriptsFromDB } = await import('../api/database');
          const dbResult = await getScriptsFromDB();
          if (dbResult.success && dbResult.scripts.length > 0) {
            dbScripts = dbResult.scripts;
          } else {
            // console.log('📭 数据库中没有剧本数据，使用示例剧本');
          }
        } catch (error) {
        }
        
        // 获取示例剧本
        const exampleScripts = getExampleScripts();
        
        // 合并数据库剧本和示例剧本
        const mergedScripts = [...exampleScripts];
        
        // 用数据库中的剧本覆盖示例剧本
        dbScripts.forEach(dbScript => {
          const existingIndex = mergedScripts.findIndex(ex => ex.id === dbScript.id);
          if (existingIndex >= 0) {
            const example = mergedScripts[existingIndex];
            // 简化数据库的剧本列表省略证物字段，保留示例剧本自带的证物。
            mergedScripts[existingIndex] = { ...dbScript, evidences: dbScript.evidences ?? example.evidences };
          } else {
            // 如果是新剧本，添加到列表
            mergedScripts.push(dbScript);
            // console.log('➕ 添加数据库新剧本:', dbScript.id);
          }
        });

        // 迁移：若缺少玩家/搭档/凶手，从示例模板补齐
        const ensureRolesFromExample = (script: Script): Script => {
          const example = exampleScripts.find(e => e.id === script.id);
          if (!example) return script;

          const hasPlayer = script.characters.some(c => c.isPlayer);
          const hasPartner = script.characters.some(c => c.isPartner);
          const hasKiller = script.characters.some(c => c.isKiller);

          const updated = { ...script, characters: [...script.characters], settings: { ...script.settings } };

          if (!hasPlayer) {
            const examplePlayer = example.characters.find(c => c.isPlayer);
            if (examplePlayer) {
              const idx = updated.characters.findIndex(c => c.name === examplePlayer.name);
              if (idx >= 0) {
                updated.characters[idx] = { ...updated.characters[idx], isPlayer: true, isDetective: false, roleType: '玩家' } as any;
              } else {
                updated.characters.unshift(examplePlayer);
              }
              updated.settings.playerName = examplePlayer.name;
              updated.settings.playerRole = examplePlayer.name;
            }
          }

          if (!hasPartner) {
            const examplePartner = example.characters.find(c => c.isPartner);
            if (examplePartner) {
              const idx = updated.characters.findIndex(c => c.name === examplePartner.name);
              if (idx >= 0) {
                updated.characters[idx] = { ...updated.characters[idx], isPartner: true, isAssistant: true, roleType: '搭档', isDetective: false } as any;
              } else {
                updated.characters.push(examplePartner);
              }
              updated.settings.partnerRole = examplePartner.name;
            }
          }

          if (!hasKiller) {
            const exampleKiller = example.characters.find(c => c.isKiller);
            if (exampleKiller) {
              const idx = updated.characters.findIndex(c => c.name === exampleKiller.name);
              if (idx >= 0) {
                updated.characters[idx] = { ...updated.characters[idx], isKiller: true, roleType: '凶手' } as any;
              } else {
                updated.characters.push(exampleKiller);
              }
              updated.settings.killerRole = exampleKiller.name;
            }
          }

          return updated;
        };

        const migratedScripts = mergedScripts.map(ensureRolesFromExample);

        // 过滤掉已删除的剧本
        const filteredScripts = filterDeletedScripts(migratedScripts);

        // 直接设置剧本数据，不再使用localStorage
        setScripts(filteredScripts);
        
        // 如果是首次使用，保存示例剧本到数据库
        if (dbScripts.length === 0) {
          const { saveScriptToDB } = await import('../api/database');
          for (const script of exampleScripts) {
            try {
              await saveScriptToDB(script);
            } catch (error) {
            }
          }
        } else {
        }

        // 尝试加载当前剧本
        const currentScriptId = getCurrentScriptId();
        if (currentScriptId) {
          const script = findScriptById(filteredScripts, currentScriptId);
          if (script) {
            setCurrentScript(script);
          }
        } else {
          // 如果没有当前剧本，默认加载"深宫血色：玉玺谜云"
          const defaultScript = findScriptById(filteredScripts, 'example_4');
          if (defaultScript) {
            setCurrentScript(defaultScript);
            setCurrentScriptId('example_4');
          } else {
            // 如果找不到深宫血色剧本，加载第一个可用剧本
            const firstScript = filteredScripts[0];
            if (firstScript) {
              setCurrentScript(firstScript);
              setCurrentScriptId(firstScript.id);
            }
          }
        }
      } catch (error) {
        console.error('❌ 初始化剧本数据失败:', error);
        // 降级到示例剧本，但也要过滤已删除的
        const exampleScripts = getExampleScripts();
        const filteredExampleScripts = filterDeletedScripts(exampleScripts);
        setScripts(filteredExampleScripts);
      }
    };

    initializeScripts();
  }, []);

  // 加载指定剧本
  const loadScript = (id: string) => {
    const script = findScriptById(scripts, id);
    if (script) {
      setCurrentScript(script);
      setCurrentScriptId(id);
    }
  };

  // 保存剧本
  const saveScript = async (script: Script) => {
    const updatedScript = {
      ...script,
      updatedAt: new Date().toISOString(),
      sourceType: script.sourceType || 'manual'
    };

    try {
      // 统一保存到数据库
      const result = await saveScriptToDB(updatedScript);
      
      if (result.success) {
        
        // 更新内存中的剧本列表
        setScripts(prevScripts => {
          const existingIndex = prevScripts.findIndex(s => s.id === script.id);
          if (existingIndex >= 0) {
            const newScripts = [...prevScripts];
            newScripts[existingIndex] = updatedScript;
            return newScripts;
          } else {
            return [...prevScripts, updatedScript];
          }
        });

        // 如果保存的是当前剧本，更新当前剧本
        if (currentScript && currentScript.id === script.id) {
          setCurrentScript(updatedScript);
        }
      } else {
        console.error('❌ 剧本保存到数据库失败:', result.message);
        throw new Error(result.message || '数据库保存失败');
      }
    } catch (error) {
      console.error('❌ 保存剧本失败:', error);
      // 降级到原有的localStorage保存
      
      try {
        // 根据sourceType决定保存方式
        if (updatedScript.sourceType === 'ai') {
          const { optimizeScriptStorage } = await import('../utils/storageManager');
          const savedAIScripts = localStorage.getItem('ai_generated_scripts');
          let aiScripts: Script[] = [];
          
          if (savedAIScripts) {
            aiScripts = JSON.parse(savedAIScripts);
          }
          
          const existingIndex = aiScripts.findIndex(s => s.id === updatedScript.id);
          if (existingIndex >= 0) {
            aiScripts[existingIndex] = updatedScript;
          } else {
            aiScripts.push(updatedScript);
          }
          
          // 优化存储前检查空间
          try {
            const optimizedScripts = optimizeScriptStorage(aiScripts);
            localStorage.setItem('ai_generated_scripts', JSON.stringify(optimizedScripts));
          } catch (quotaError) {
            if (quotaError instanceof DOMException && quotaError.name === 'QuotaExceededError') {
              console.warn('⚠️ localStorage配额超出，开始清理旧数据...');
              
              // 只保留最近的20个剧本
              const recentScripts = aiScripts
                .sort((a, b) => new Date(b.updatedAt || b.createdAt || 0).getTime() - new Date(a.updatedAt || a.createdAt || 0).getTime())
                .slice(0, 20);
              
              const optimizedRecentScripts = optimizeScriptStorage(recentScripts);
              localStorage.setItem('ai_generated_scripts', JSON.stringify(optimizedRecentScripts));
              
              console.log(`✅ 清理完成，保留了 ${recentScripts.length} 个最近的剧本`);
            } else {
              throw quotaError;
            }
          }
        } else {
          // 保存到数据库
          try {
            const { saveScriptToDB } = await import('../api/database');
            const result = await saveScriptToDB(updatedScript);
            if (!result.success) {
              throw new Error('数据库保存失败');
            }
          } catch (error) {
            throw new Error('数据库保存失败');
          }
        }
        
        // 更新内存状态
        setScripts(prevScripts => {
          const existingIndex = prevScripts.findIndex(s => s.id === script.id);
          if (existingIndex >= 0) {
            const newScripts = [...prevScripts];
            newScripts[existingIndex] = updatedScript;
            return newScripts;
          } else {
            return [...prevScripts, updatedScript];
          }
        });
        
        if (currentScript && currentScript.id === script.id) {
          setCurrentScript(updatedScript);
        }
      } catch (fallbackError) {
        console.error('❌ 降级保存也失败:', fallbackError);
        throw fallbackError;
      }
    }
  };

  // 更新剧本（保存到数据库）
  const updateScript = async (script: Script): Promise<void> => {
    
    // 保存到数据库
    try {
      const { saveScriptToDB } = await import('../api/database');
      const result = await saveScriptToDB(script);
      if (result.success) {
      } else {
      }
    } catch (error) {
      console.error('❌ 数据库保存异常:', error);
    }
    
    // 更新内存中的剧本列表
    setScripts(prevScripts => {
      const existingIndex = prevScripts.findIndex(s => s.id === script.id);
      if (existingIndex >= 0) {
        const newScripts = [...prevScripts];
        newScripts[existingIndex] = script;
        return newScripts;
      } else {
        return [...prevScripts, script];
      }
    });

    // 如果更新的是当前剧本，更新当前剧本
    if (currentScript && currentScript.id === script.id) {
      setCurrentScript(script);
    }
  };

  // 删除剧本 - 完善版本，确保所有数据源同步
  const deleteScript = async (id: string) => {
    try {
      console.log(`🗑️ 开始删除剧本: ${id}`);
      
      // 找到要删除的剧本
      const scriptToDelete = scripts.find(s => s.id === id);
      if (!scriptToDelete) {
        console.warn('⚠️ 未找到要删除的剧本:', id);
        return;
      }

      console.log(`📝 剧本信息: ${scriptToDelete.title} (${scriptToDelete.sourceType || 'unknown'})`);

      // 1. 根据剧本类型执行相应的删除操作
      if (scriptToDelete.sourceType === 'ai') {
        // AI生成的剧本从localStorage删除
        console.log('🤖 删除AI生成剧本...');
        const savedAIScripts = localStorage.getItem('ai_generated_scripts');
        if (savedAIScripts) {
          try {
            const aiScripts = JSON.parse(savedAIScripts);
            const filteredScripts = aiScripts.filter((s: Script) => s.id !== id);
            localStorage.setItem('ai_generated_scripts', JSON.stringify(filteredScripts));
            console.log('✅ AI剧本localStorage删除成功');
          } catch (error) {
            console.error('❌ 从localStorage删除AI剧本失败:', error);
          }
        }
      } else {
        // 手动创建的剧本从文件系统删除
        console.log('📁 删除手动创建剧本文件...');
        const fileDeleted = await deleteScriptFile(id);
        if (fileDeleted) {
          console.log('✅ 剧本文件删除成功');
        } else {
          console.warn('⚠️ 文件删除失败，但继续删除操作');
        }
      }

      // 2. 尝试从数据库删除（无论什么类型都尝试）
      console.log('🗄️ 从数据库删除剧本...');
      try {
        const dbResult = await deleteScriptFromDB(id);
        if (dbResult.success) {
          console.log('✅ 数据库删除成功');
        } else {
          console.log('⚠️ 数据库删除失败或剧本不存在于数据库:', dbResult.message);
        }
      } catch (error) {
        console.warn('⚠️ 数据库删除操作失败，但继续删除:', error);
      }

      // 3. 标记为已删除状态（持久化删除记录）
      console.log('📋 记录删除状态...');
      const sourceType = scriptToDelete.id.startsWith('example_') ? 'example' : 
                        scriptToDelete.sourceType === 'ai' ? 'ai' : 
                        scriptToDelete.sourceType || 'manual';
      
      markScriptAsDeleted(id, sourceType as any, scriptToDelete.title);
      
      // 4. 从当前状态删除
      console.log('🔄 更新当前状态...');
      setScripts(prevScripts => {
        const newScripts = prevScripts.filter(script => script.id !== id);
        return newScripts;
      });
      
      // 5. 如果删除的是当前剧本，清空当前剧本
      if (currentScript && currentScript.id === id) {
        console.log('🎯 清空当前剧本状态');
        setCurrentScript(null);
        setCurrentScriptId('');
      }

      console.log('✅ 剧本删除完成:', id);
      
    } catch (error) {
      console.error('❌ 删除剧本失败:', error);
      throw error; // 向上层抛出错误，便于UI处理
    }
  };

  // 创建新剧本
  const createNewScript = async () => {
    const newScript = createNewScriptTemplate();
    
    try {
      // 保存到数据库
      const { saveScriptToDB } = await import('../api/database');
      const result = await saveScriptToDB(newScript);
      if (result.success) {
      } else {
      }

      // 更新内存中的剧本列表
      setScripts(prevScripts => {
        const newScripts = [...prevScripts, newScript];
        // 数据直接保存到数据库，不需要localStorage备份
        return newScripts;
      });
      
      // 将新剧本设置为当前编辑对象
      setCurrentScript(newScript);
      setCurrentScriptId(newScript.id);
      return newScript;
    } catch (error) {
      console.error('❌ 创建新剧本失败:', error);
      // 降级处理
      setScripts(prevScripts => {
        const newScripts = [...prevScripts, newScript];
        // 数据直接保存到数据库，不需要localStorage备份
        return newScripts;
      });
      setCurrentScript(newScript);
      setCurrentScriptId(newScript.id);
      return newScript;
    }
  };

  const value: ScriptContextType = {
    currentScript,
    scripts,
    loadScript,
    saveScript,
    deleteScript,
    createNewScript,
    updateScript
  };

  return (
    <ScriptContext.Provider value={value}>
      {children}
    </ScriptContext.Provider>
  );
};

// 自定义 Hook 用于使用 ScriptContext
export const useScriptContext = () => {
  const context = useContext(ScriptContext);
  if (context === undefined) {
    throw new Error('useScriptContext must be used within a ScriptProvider');
  }
  return context;
};

