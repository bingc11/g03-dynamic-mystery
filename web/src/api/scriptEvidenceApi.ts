/**
 * 剧本证物实时保存API
 * 负责处理证物级别的独立保存和同步
 */

import { ScriptEvidence } from '../types/script';

import { API_URL as API_BASE_URL } from '../constants';

export interface EvidenceSaveResponse {
  success: boolean;
  evidence?: ScriptEvidence;
  message?: string;
  error?: string;
}

export interface EvidenceListResponse {
  success: boolean;
  evidences: ScriptEvidence[];
  count: number;
  error?: string;
}

/**
 * 单独保存/更新剧本证物
 */
export const saveScriptEvidence = async (
  evidence: ScriptEvidence,
  scriptId: string
): Promise<EvidenceSaveResponse> => {
  try {
    console.log('💾 保存证物到数据库:', evidence.name);
    
    const evidenceData = {
      ...evidence,
      scriptId // 确保包含scriptId
    };
    
    const response = await fetch(`${API_BASE_URL}/db/evidences/save`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(evidenceData),
    });

    const data = await response.json();
    
    if (!response.ok) {
      return {
        success: false,
        error: data.detail || `HTTP ${response.status}: ${response.statusText}`
      };
    }

    console.log('✅ 证物保存成功:', data.evidence?.name);
    return {
      success: true,
      evidence: data.evidence,
      message: data.message
    };
  } catch (error) {
    console.error('❌ 保存证物失败:', error);
    return {
      success: false,
      error: error instanceof Error ? error.message : '保存证物失败'
    };
  }
};

/**
 * 删除剧本证物
 */
export const deleteScriptEvidence = async (
  evidenceId: string,
  scriptId: string
): Promise<{ success: boolean; message?: string; error?: string }> => {
  try {
    console.log('🗑️ 删除证物:', evidenceId);
    
    const response = await fetch(`${API_BASE_URL}/db/evidences/${evidenceId}`, {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    const data = await response.json();
    
    if (!response.ok) {
      return {
        success: false,
        error: data.detail || `HTTP ${response.status}: ${response.statusText}`
      };
    }

    console.log('✅ 证物删除成功');
    return {
      success: true,
      message: data.message
    };
  } catch (error) {
    console.error('❌ 删除证物失败:', error);
    return {
      success: false,
      error: error instanceof Error ? error.message : '删除证物失败'
    };
  }
};

/**
 * 获取剧本的所有证物
 */
export const getScriptEvidences = async (
  scriptId: string
): Promise<EvidenceListResponse> => {
  try {
    console.log('📖 从数据库加载证物:', scriptId);
    
    const response = await fetch(`${API_BASE_URL}/db/evidences/script/${scriptId}`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    const data = await response.json();
    
    if (!response.ok) {
      return {
        success: false,
        evidences: [],
        count: 0,
        error: data.detail || `HTTP ${response.status}: ${response.statusText}`
      };
    }

    const evidences = data.evidences || [];
    const count = evidences.length;
    console.log(`✅ 加载证物成功，共 ${count} 个`);
    return {
      success: true,
      evidences: evidences,
      count: count
    };
  } catch (error) {
    console.error('❌ 加载证物失败:', error);
    return {
      success: false,
      evidences: [],
      count: 0,
      error: error instanceof Error ? error.message : '加载证物失败'
    };
  }
};

/**
 * 批量保存证物
 */
export const saveMultipleEvidences = async (
  evidences: ScriptEvidence[],
  scriptId: string
): Promise<{ 
  success: boolean; 
  successCount: number; 
  failedCount: number; 
  errors: string[];
}> => {
  const results = await Promise.allSettled(
    evidences.map(evidence => saveScriptEvidence(evidence, scriptId))
  );
  
  let successCount = 0;
  let failedCount = 0;
  const errors: string[] = [];
  
  results.forEach((result, index) => {
    if (result.status === 'fulfilled' && result.value.success) {
      successCount++;
    } else {
      failedCount++;
      const error = result.status === 'rejected' 
        ? result.reason?.message || '未知错误'
        : result.value.error || '保存失败';
      errors.push(`证物 ${evidences[index].name}: ${error}`);
    }
  });
  
  return {
    success: failedCount === 0,
    successCount,
    failedCount,
    errors
  };
};
