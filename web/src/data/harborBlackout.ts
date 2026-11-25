import type { Script } from '../types/script';

export const harborBlackout: Script = {
  id: 'harbor_blackout',
  npcManaged: true,
  title: '雾港停电案',
  description: '雾港的仓库短暂停电，一名货运审计员在过磅间遇害。两名目击者记下了不同的时间，调查要从西门值守、监控校时和一张残缺的过磅联入手。',
  author: 'G03',
  version: '1.0.0',
  createdAt: '2026-11-25T00:00:00.000Z',
  updatedAt: '2026-11-25T00:00:00.000Z',
  sourceType: 'manual',
  globalStory: '清晨六点二十分，货运审计员程砚被发现死在雾港旧仓库的过磅间。值班人员发现门锁完好，桌上有半张过磅联。前一晚二十一点四十分起，港区按工单暂停供电，预计六分钟。西门的门卫和仓库的卸货员都提到有个穿反光背心的人，其中一人记的是二十一点四十六分，另一人在仓库监控屏上看到的是二十一点五十四分。两人都没有看见脸。调查员裴宁受命查清两份证词是否说的是同一次出入，并追查程砚遇害的原因。宋屿负责协助调查，可联络值守人员。西门由阮岑当班，林遥负责检修，罗钧当夜负责货物过磅。',
  characters: [
    {
      name: '裴宁',
      bio: '受命来雾港调查旧仓库死亡案件的调查员。',
      personality: '做事讲究时序和可追查的来源。',
      context: '你负责询问相关人员、核对材料、指认真凶。',
      secret: '',
      violation: '只能根据证据得出结论。',
      image: 'officer.png',
      isPlayer: true,
      roleType: '玩家'
    },
    {
      name: '宋屿',
      bio: '负责协助裴宁的港口警员，熟悉当班门卫及设备检修人员。',
      personality: '耐心但谨慎，习惯把口头说法和原记录分开。',
      context: '你知道西门停电期间仍有人值守，可以帮裴宁向当班门卫问话。',
      secret: '',
      violation: '陈述目击者的说法时指出来源，保留身份未明的部分。',
      image: 'officer.png',
      isAssistant: true,
      isPartner: true,
      roleType: '搭档'
    },
    {
      name: '阮岑',
      bio: '西门夜班门卫，负责停电时手记人员出入及保管夜班器材领用表。',
      personality: '惜字如金，习惯多看一遍自己的记录才下判断。',
      context: '你负责西门的夜班出入登记。',
      secret: '',
      violation: '不能声称自己目击了访客的身份。器具领用情况要按领用表核实。',
      image: 'innocent.png',
      roleType: '嫌疑人'
    },
    {
      name: '林遥',
      bio: '港区设备检修电工，负责复电与时钟对照。',
      personality: '说话直接。比起推测，习惯翻找工单和日志。',
      context: '你负责设备检修和复电记录。',
      secret: '',
      violation: '没有比对日志前只说自己观察到的差异。',
      image: 'amateur.png',
      roleType: '嫌疑人'
    },
    {
      name: '罗钧',
      bio: '旧仓库的夜班主管，管理过磅间与货运账本。',
      personality: '守规矩的样子，谈到旧货账时容易转移话题。',
      context: '你负责夜航四号的过磅。',
      secret: '',
      violation: '提到货运账目时以已经核实的资料为准。',
      image: 'solitary.png',
      roleType: '嫌疑人'
    },
    {
      name: '程砚',
      bio: '港区货运审计员，正复核夜航四号的申报重量。',
      personality: '严谨，碰到单据矛盾总会保留复写件。',
      context: '你是本案受害人。',
      secret: '',
      violation: '作为受害人无法参与游戏对话。',
      image: 'officer.png',
      isVictim: true,
      roleType: '受害人'
    }
  ],
  settings: {
    theme: '现代港口',
    difficulty: 'medium',
    estimatedDuration: 25,
    playerName: '裴宁',
    playerRole: '裴宁',
    partnerRole: '宋屿'
  },
  evidences: [
    {
      id: 'harbor_work_order',
      name: '停电检修工单',
      description: '市电计划在二十一点四十分停供，预计六分钟。西门门禁在停电期间由当班门卫手记。',
      category: 'document',
      importance: 'high',
      relatedCharacters: ['宋屿', '阮岑', '林遥'],
      initialState: 'surface'
    },
    {
      id: 'harbor_clock_strip',
      name: '监控校时便条',
      description: '维修人员提醒，复电后监控屏时钟需要与北塔标准钟对时。便条没有记录偏差。',
      category: 'document',
      importance: 'high',
      relatedCharacters: ['林遥', '宋屿'],
      initialState: 'surface'
    },
    {
      id: 'harbor_weight_slip',
      name: '半张过磅联',
      description: '同一批货物留下两处不同重量。折口压着「夜航四号」的单号。',
      category: 'document',
      importance: 'critical',
      relatedCharacters: ['程砚', '罗钧'],
      initialState: 'surface'
    }
  ]
};
