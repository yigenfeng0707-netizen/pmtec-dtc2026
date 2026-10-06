/* PMTEC 技术方案 Word 文档生成器 — docx-js
 * 架构：R4 封面(GO-1) / 前置(摘要+目录, Roman) / 正文(Arabic) 三节
 * 数据：全部数字来自仓库真实产物（五问报告/MC结果/置信报告/git log）
 */
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  ImageRun, PageBreak, Header, Footer, PageNumber, NumberFormat,
  AlignmentType, HeadingLevel, WidthType, BorderStyle, ShadingType,
  TableLayoutType, TableOfContents, SectionType,
} = require("docx");
const fs = require("fs");
const path = require("path");

let sizeOf;
try { sizeOf = require("image-size").imageSize || require("image-size"); }
catch (e) { sizeOf = null; }

const ROOT = path.resolve(__dirname, "..");
const FIGS = path.join(ROOT, "pmtec_system", "output", "techdoc_figs");
const OUT = path.join(__dirname, "PMTEC-技术方案.docx");

/* ── GO-1 Graphite Orange 调色板 ── */
const P = {
  bg: "1A2330", accent: "D4875A",
  cover: { titleColor: "FFFFFF", subtitleColor: "B0B8C0", metaColor: "90989F", footerColor: "687078" },
  table: { headerBg: "D4875A", headerText: "FFFFFF", accentLine: "D4875A", innerLine: "DDD0C8", surface: "F8F0EB" },
};
const INK = "1A2330";      // 正文标题色
const BODY = "000000";      // Profile A 正文纯黑
const GREY = "808080";

const NB = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const noBorders = { top: NB, bottom: NB, left: NB, right: NB };
const allNoBorders = { top: NB, bottom: NB, left: NB, right: NB, insideHorizontal: NB, insideVertical: NB };

function safeText(v, ph) {
  if (v === undefined || v === null || v === "" || String(v) === "NaN" || String(v) === "undefined")
    return ph || "【待补充】";
  return String(v);
}

/* ── 封面标题布局（design-system 标准实现） ── */
function splitTitleLines(title, charsPerLine) {
  if (title.length <= charsPerLine) return [title];
  const breakAfter = new Set([..."，。、；：！？", ..."的与和及之在于为", ..."-_—–·/", ..." \t"]);
  const lines = [];
  let remaining = title;
  while (remaining.length > charsPerLine) {
    let breakAt = -1;
    for (let i = charsPerLine; i >= Math.floor(charsPerLine * 0.6); i--) {
      if (i < remaining.length && breakAfter.has(remaining[i - 1])) { breakAt = i; break; }
    }
    if (breakAt === -1) {
      const limit = Math.min(remaining.length, Math.ceil(charsPerLine * 1.3));
      for (let i = charsPerLine + 1; i < limit; i++) {
        if (breakAfter.has(remaining[i - 1])) { breakAt = i; break; }
      }
    }
    if (breakAt === -1) {
      breakAt = charsPerLine;
      const prevChar = remaining[breakAt - 1], nextChar = remaining[breakAt];
      if (prevChar && nextChar && !breakAfter.has(prevChar) && !breakAfter.has(nextChar) &&
          /[\u4e00-\u9fff]/.test(prevChar) && /[\u4e00-\u9fff]/.test(nextChar)) breakAt -= 1;
    }
    lines.push(remaining.slice(0, breakAt).trim());
    remaining = remaining.slice(breakAt).trim();
  }
  if (remaining) lines.push(remaining);
  if (lines.length > 1 && lines[lines.length - 1].length <= 2) {
    const last = lines.pop();
    lines[lines.length - 1] += last;
  }
  return lines;
}

function calcTitleLayout(title, maxWidthTwips, preferredPt = 40, minPt = 24) {
  const charsPerLine = (pt) => Math.floor(maxWidthTwips / (pt * 20));
  let titlePt = preferredPt, lines;
  while (titlePt >= minPt) {
    const cpl = charsPerLine(titlePt);
    if (cpl < 2) { titlePt -= 2; continue; }
    lines = splitTitleLines(title, cpl);
    if (lines.length <= 3) break;
    titlePt -= 2;
  }
  if (!lines || lines.length > 3) {
    lines = splitTitleLines(title, charsPerLine(minPt));
    titlePt = minPt;
  }
  return { titlePt, titleLines: lines };
}

/* ── R4 封面：顶部色块 + 分隔条 + 白色下半区 ── */
function buildCoverR4(config) {
  const padL = 1200, padR = 800;
  const availableWidth = 11906 - padL - padR;
  let { titlePt, titleLines } = calcTitleLayout(config.title, availableWidth, 40, 26);
  if (config.titleLinesOverride) {
    titleLines = config.titleLinesOverride;
    const widest = Math.max(...titleLines.map(l =>
      [...l].reduce((a, ch) => {
        const c = ch.codePointAt(0);
        return a + ((c >= 0x4e00 && c <= 0x9fff) ? 20 : 11);
      }, 0)));
    titlePt = Math.max(26, Math.min(titlePt, Math.floor(availableWidth / widest)));
  }
  const titleSize = titlePt * 2;
  const titleBlockHeight = titleLines.length * (titlePt * 23 + 200);
  const englishLabelH = config.englishLabel ? (9 * 23 + 500) : 0;
  const subtitleH = config.subtitle ? (12 * 23 + 200) : 0;
  const upperContentH = englishLabelH + titleBlockHeight + subtitleH;
  const UPPER_MIN = 7500;
  const UPPER_H = Math.max(UPPER_MIN, upperContentH + 1500 + 800);
  const DIVIDER_H = 60;
  const spacerIntrinsic = 280;
  const topSpacing = Math.max(UPPER_H - upperContentH - spacerIntrinsic - 800, 400);

  const upperBlock = new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    layout: TableLayoutType.FIXED,
    borders: allNoBorders,
    rows: [new TableRow({
      height: { value: UPPER_H, rule: "exact" },
      children: [new TableCell({
        shading: { type: ShadingType.CLEAR, fill: P.bg }, borders: noBorders,
        verticalAlign: "top",
        margins: { left: padL, right: padR },
        children: [
          new Paragraph({ spacing: { before: topSpacing } }),
          config.englishLabel ? new Paragraph({
            spacing: { after: 500 },
            children: [new TextRun({ text: config.englishLabel.split("").join(" "),
              size: 18, color: P.accent, font: { ascii: "Calibri" }, characterSpacing: 60 })],
          }) : null,
          ...titleLines.map((line, i) => new Paragraph({
            spacing: { after: i < titleLines.length - 1 ? 100 : 200, line: Math.ceil(titlePt * 23), lineRule: "atLeast" },
            children: [new TextRun({ text: line, size: titleSize, bold: true,
              color: P.cover.titleColor, font: { eastAsia: "SimHei", ascii: "Arial" } })],
          })),
          config.subtitle ? new Paragraph({
            spacing: { after: 100 },
            children: [new TextRun({ text: config.subtitle, size: 24, color: P.cover.subtitleColor,
              font: { eastAsia: "Microsoft YaHei", ascii: "Arial" } })],
          }) : null,
        ].filter(Boolean),
      })],
    })],
  });

  const divider = new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    borders: allNoBorders,
    rows: [new TableRow({
      height: { value: DIVIDER_H, rule: "exact" },
      children: [new TableCell({ borders: noBorders,
        shading: { type: ShadingType.CLEAR, fill: P.accent },
        children: [new Paragraph({})] })],
    })],
  });

  const lowerContent = [
    new Paragraph({ spacing: { before: 800 } }),
    ...(config.metaLines || []).map(line => new Paragraph({
      indent: { left: padL }, spacing: { after: 100 },
      children: [new TextRun({ text: safeText(line), size: 28, color: P.cover.metaColor,
        font: { eastAsia: "Microsoft YaHei", ascii: "Arial" } })],
    })),
    new Paragraph({ spacing: { before: 2000 } }),
    new Paragraph({
      indent: { left: padL },
      children: [
        new TextRun({ text: config.footerLeft || "", size: 22, color: "909090" }),
        new TextRun({ text: "          " }),
        new TextRun({ text: config.footerRight || "", size: 22, color: "909090" }),
      ],
    }),
  ];

  return [new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    layout: TableLayoutType.FIXED,
    borders: allNoBorders,
    rows: [new TableRow({
      height: { value: 16838, rule: "exact" },
      children: [new TableCell({
        shading: { type: ShadingType.CLEAR, fill: "FFFFFF" }, borders: noBorders,
        verticalAlign: "top",
        children: [upperBlock, divider, ...lowerContent],
      })],
    })],
  })];
}

/* ── 正文构件 ── */
function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 360, after: 160, line: 312 },
    children: [new TextRun({ text, bold: true, size: 32, color: INK,
      font: { eastAsia: "SimHei", ascii: "Times New Roman" } })],
  });
}
function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 240, after: 120, line: 312 },
    children: [new TextRun({ text, bold: true, size: 28, color: INK,
      font: { eastAsia: "SimHei", ascii: "Times New Roman" } })],
  });
}
function h3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    spacing: { before: 200, after: 100, line: 312 },
    children: [new TextRun({ text, bold: true, size: 24, color: INK,
      font: { eastAsia: "SimHei", ascii: "Times New Roman" } })],
  });
}
function body(text, opts = {}) {
  const runs = Array.isArray(text) ? text : [new TextRun({ text, size: 24, color: BODY,
    font: { eastAsia: "SimSun", ascii: "Times New Roman" } })];
  return new Paragraph({
    alignment: AlignmentType.JUSTIFIED,
    indent: { firstLine: 480 },
    spacing: { line: 312, after: opts.after ?? 0 },
    children: runs,
  });
}
function bt(text, bold = false) {
  return new TextRun({ text, bold, size: 24, color: BODY,
    font: { eastAsia: "SimSun", ascii: "Times New Roman" } });
}
function figure(file, caption, displayWidth = 560) {
  const p = path.join(FIGS, file);
  const buf = fs.readFileSync(p);
  let w = 1100, h = 720;
  try {
    const dim = sizeOf(buf);
    w = dim.width; h = dim.height;
  } catch (e) { /* fallback defaults */ }
  const displayHeight = Math.round(displayWidth * h / w);
  return [
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 120 },
      children: [new ImageRun({ data: buf, type: "png",
        transformation: { width: displayWidth, height: displayHeight } })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 200 },
      children: [new TextRun({ text: caption, size: 21, color: "555555",
        font: { eastAsia: "SimSun", ascii: "Times New Roman" } })],
    }),
  ];
}
function dataTable(caption, headers, rows, colPct) {
  const headerRow = new TableRow({
    tableHeader: true, cantSplit: true,
    children: headers.map((t, i) => new TableCell({
      shading: { type: ShadingType.CLEAR, fill: P.table.headerBg },
      margins: { top: 70, bottom: 70, left: 120, right: 120 },
      width: { size: colPct[i], type: WidthType.PERCENTAGE },
      children: [new Paragraph({ alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: t, bold: true, size: 21, color: P.table.headerText,
          font: { eastAsia: "SimHei", ascii: "Times New Roman" } })] })],
    })),
  });
  const dataRows = rows.map(r => new TableRow({
    cantSplit: true,
    children: r.map((t, i) => new TableCell({
      margins: { top: 60, bottom: 60, left: 120, right: 120 },
      width: { size: colPct[i], type: WidthType.PERCENTAGE },
      children: [new Paragraph({ alignment: i === 0 ? AlignmentType.LEFT : AlignmentType.CENTER,
        children: [new TextRun({ text: safeText(t), size: 21, color: BODY,
          font: { eastAsia: "SimSun", ascii: "Times New Roman" } })] })],
    })),
  }));
  return [
    new Paragraph({
      keepNext: true, spacing: { before: 160, after: 80 },
      alignment: AlignmentType.CENTER,
      children: [new TextRun({ text: caption, bold: true, size: 21, color: INK,
        font: { eastAsia: "SimHei", ascii: "Times New Roman" } })],
    }),
    new Table({
      width: { size: 100, type: WidthType.PERCENTAGE },
      borders: {
        top: { style: BorderStyle.SINGLE, size: 4, color: P.table.accentLine },
        bottom: { style: BorderStyle.SINGLE, size: 4, color: P.table.accentLine },
        left: NB, right: NB,
        insideHorizontal: { style: BorderStyle.SINGLE, size: 1, color: P.table.innerLine },
        insideVertical: NB,
      },
      rows: [headerRow, ...dataRows],
    }),
    new Paragraph({ spacing: { after: 120 }, children: [] }),
  ];
}

/* ── 页眉页脚 ── */
function pageHeader() {
  return new Header({ children: [new Paragraph({
    alignment: AlignmentType.CENTER,
    border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: P.table.innerLine } },
    children: [new TextRun({ text: "PMTEC 数字孪生战场系统技术方案", size: 18, color: GREY,
      font: { eastAsia: "SimSun" } })],
  })] });
}
function pageFooter() {
  return new Footer({ children: [new Paragraph({
    alignment: AlignmentType.CENTER,
    children: [new TextRun({ children: [PageNumber.CURRENT], size: 18, color: GREY })],
  })] });
}

/* ══════════ 正文内容 ══════════ */
const bodyChildren = [];

/* 第 1 章 */
bodyChildren.push(h1("一、项目概述与问题定义"));
bodyChildren.push(h2("1.1 问题定义：政治拒止下的体系韧性"));
bodyChildren.push(body("PMTEC（Pacific Multi-domain Training and Experimentation Capability，印太多域训练与实验能力）数字孪生战场系统，回答一个传统仿真系统未曾覆盖的问题：当对手不开一枪、仅通过政治手段使盟国拒绝提供基地使用权时，防空体系的作战韧性如何演化、如何保障。该问题源于印太战区的现实威胁图景——前沿基地体系高度依赖东道国准入，而政治拒止（灰色地带施压、主权打击胁迫）可以在不触发热战的情况下掏空体系前沿。"));
bodyChildren.push(body([
  bt("本项目将政治准入作为仿真状态机的一等公民纳入闭环，而不是一句背景设定。"),
  bt("每个盟友站点具有 Open / Restricted / Denied 三态，政治事件注入后当周期即响应；决策侧 DQN 的 219 维观测显式包含每个站点的准入容量因子，部署优化器将政治风险敞口作为 Pareto 第六目标显式压制。体系在政治拒止下的表现可概括为：引入政治约束后拦截率不降反稳——三场景对照为 76.2% → 79.0% → 79.1%，这是本方案最具颠覆性的独立判断（详见第五章）。", true),
]));
bodyChildren.push(h2("1.2 DTB 模型四组件映射"));
bodyChildren.push(body("系统严格按照数字孪生战场（DTB）模型的四组件规格完成映射，并以 433 行 protobuf 接口契约固化："));
bodyChildren.push(...dataTable("表 1：DTB 四组件映射",
  ["组件", "规格要求", "本系统实现", "关键证据"],
  [
    ["作战引擎", "仿真推演驱动 ASDA 闭环", "PMTECEngine 每 10 秒完整执行 Act-Sense-Decide-Adapt", "grpc_server / 仿真报告"],
    ["战斗网络", "传感器聚合分析", "Kalman 滤波 + JPDA 多源航迹融合，67 节点战斗网络", "track.py / 融合报告"],
    ["应用商店", "能力模块化热加载", "PluginManager + REST 网关 + DQN 推理服务", "dt_platform / 28 端点"],
    ["即插即用", "标准接口互操作", "gRPC 4 服务（433 行 proto）+ REST Maven 契约", "proto / 契约清单"],
  ], [14, 24, 38, 24]));
bodyChildren.push(body("三级交付齐备：第一级 ASDA 算法原型（GIS 标绘与仿真验证），第二级基地部署优化工程（可运行的优化器与三指标实测），第三级 PMTEC 系统（本项目主体，157 次提交、167 个 Python 文件、约 4.3 万行代码，32 天完成）。"));

/* 第 2 章 */
bodyChildren.push(h1("二、总体架构设计"));
bodyChildren.push(body("系统采用六层架构，自下而上依次为数据与基础设施层、仿真引擎层、孪生服务层、本体语义层、智能决策层和应用与展示层。层间通过 gRPC/REST/WebSocket 三通道解耦，任一层的替换不影响相邻层（本体语义层保持模型无关，展示层与引擎可独立重部署）。"));
bodyChildren.push(...figure("fig1_arch.png", "图 1：PMTEC 系统六层总体架构", 580));
bodyChildren.push(h2("2.1 技术栈选型"));
bodyChildren.push(body("仿真引擎与深度强化学习基于 Python（PyTorch CPU 推理，训练期可切 XPU/GPU）；服务接口采用 gRPC（4 服务）与 REST（28 端点，OpenAPI 全量文档化）；实时推送采用 WebSocket（每 ASDA 周期广播，10 Hz 上限，环形回放缓冲）；持久化采用 SQLite WAL 模式（实测 58,228 写入/秒）；编排采用 Docker Compose 双容器（引擎 + 展示中心 nginx），安全层实现 JWT 会话与三级角色 RBAC（observer / operator / commander）。"));

/* 第 3 章 */
bodyChildren.push(h1("三、数据工程与权威底座"));
bodyChildren.push(h2("3.1 权威实体库"));
bodyChildren.push(body("数据底座为 67 个印太基地实体、34 个字段，逐字段可溯源：坐标与基地清单溯源至美国国会研究处报告 CRS R47589 Table A-1 与国防部 FY2024 Base Structure Report，兵力参数按 CRS IF12175 校准，政治参数定性依据 RAND RRA967-2。字段级来源、覆盖数与示例由数据字典生成器实跑再生（scripts/generate_data_dictionary.py），承诺「重跑即再生，数字不手填」。"));
bodyChildren.push(h2("3.2 数量口径与置信度分级"));
bodyChildren.push(body("为杜绝多口径打架，系统在 README 中维护全仓唯一口径权威表，并由 caliber_check.py 脚本在 CI 中做防漂移自检。核心口径如下："));
bodyChildren.push(...dataTable("表 2：基地数量口径权威表",
  ["数字", "权威定义", "使用位置"],
  [
    ["67", "印太基地实体总数（v2 权威库，CRS+FY2024 双源）", "一级标绘、本体层、DoDAF 投影、档案、部署优化"],
    ["22", "引擎实时推演口径（v1 库；P6/P12 观测维度与训练模型锚定）", "引擎 REST/WS 实时推演、Monte Carlo"],
    ["15", "引擎政治准入盟友站点（澳日菲韩 4 东道国；推演中 5/7/3 分布）", "P10 政治状态机、AI 参谋官报告"],
    ["36", "v2 权威库 host_nation 计数（分析管线口径）", "韧性分析、必答五问实验"],
    ["45/21/1", "置信度四级标注：A 多源核验 / A- v1 沿用 / B 降级（Tinian）/ D 待核验（留白）", "P14 置信层、基地档案"],
  ], [12, 46, 42]));
bodyChildren.push(body("全部实体、置信与溯源数据信息截至 2026-09（CRS R47589 与 DoD FY2024 BSR），后续源更新以提交历史留痕刷新。"));

/* 第 4 章 */
bodyChildren.push(h1("四、核心机制设计"));
bodyChildren.push(h2("4.1 ASDA 四相位闭环"));
bodyChildren.push(body("仿真主循环以 10 秒为周期完整执行 Act（打击/部署动作）- Sense（传感器检测与航迹融合）- Decide（DQN 拦截决策与 C2 指令）- Adapt（疏散重构与策略反哺）四相位。SPEAR 事件流逐周期记录全部状态迁移，实测单次运行产生 22 类事件共 1,506 条，与 DoDAF OV-3 信息交换矩阵 22 行逐行对账，构成机器可校验的追溯链。"));
bodyChildren.push(h2("4.2 政治准入状态机"));
bodyChildren.push(body("政治准入模型（P10）以盟友站点为粒度维护三态状态机：FULL（全面准入）、RESTRICTED（有限准入，容量折减）、DENIED（准入被拒，不可用）。状态迁移由三类事件驱动：灰色地带行动（渐进施压）、主权打击（急剧胁迫）、再保证（恢复修复）。主权打击链回放实测：灰色地带两轮加压后主权打击落地，9 个盟友站点被拒止，可用基地从 67 收缩至 58；引擎实时推演口径下（22 站、15 盟友站点）拒止 3 站、可用 19/22，与实机 REST 接口及 AI 参谋官报告逐字一致。"));
bodyChildren.push(h2("4.3 智能决策层级"));
bodyChildren.push(...dataTable("表 3：AI 决策层级（建议位与执行位分离）",
  ["层级", "算法", "用途", "训练规模", "权限"],
  [
    ["L1", "UCB1 / Q-Learning", "传感器动态选择、自适应对策", "在线学习", "执行位（资源调度）"],
    ["L2", "DQN (SB3)", "ASDA 拦截/分散决策", "200K 步 + 课程学习，219 维观测", "建议位，经指挥链 RBAC 审批"],
    ["L3", "IQL / MADDPG", "多智能体协同", "6K 步，MADDPG avg_reward 1138", "建议位"],
    ["L4", "LLM 参谋官", "态势报告生成、决策建议书", "模型可替换（HTTP 接入）", "纯建议位，无执行权"],
  ], [8, 20, 26, 26, 20]));
bodyChildren.push(body("AI 参谋官的失效行为分级降级：未配置 API Key 时接口返回 503（预期降级，主仿真链路零影响）；其提示词由代码模板拼装，用户输入不进入提示词（无提示词注入面）；输出不回写仿真状态，幻觉最坏后果是一份被驳回的建议书。"));

/* 第 5 章 */
bodyChildren.push(h1("五、量化验证与效能评估"));
bodyChildren.push(h2("5.1 三场景拦截率对照"));
bodyChildren.push(body("拦截率结论建立在三场景隔离对照之上：场景 A（原 22 站、182 维 P6 模型）76.2%，场景 B（v2 权威数据升级）79.0%——第一段 +2.8 个百分点纯粹来自数据权威化，与模型无关；场景 C（叠加政治准入与 219 维观测）79.1%——政治约束全量引入后不降反稳。基准口径 79.1% 来自六策略 150 episodes Monte Carlo（CI 78.0-80.2%），概率预测校准证据 Brier 分数 0.1128（35 个真实判定样本）。"));
bodyChildren.push(...figure("fig2_scenarios.png", "图 2：三场景拦截率对照（误差棒为 95% 置信区间）"));
bodyChildren.push(h2("5.2 失效场景与红方资源代价（必答一）"));
bodyChildren.push(...dataTable("表 4：三类失效场景与红方代价（全实跑，MC n=20,000）",
  ["失效场景", "红方弹药代价", "价值保留率", "实体保留率", "拒止站点"],
  [
    ["S1 政治拒止（灰色地带→主权打击链）", "0 发", "99.8%", "86.6%（58/67）", "9 站"],
    ["S2 动能定向打掉 30%（PAE 优先序）", "100–160 发", "28.8%", "70.2%", "含 Tier-1 枢纽 14 座"],
    ["S3 复合（政治拒止+对剩余集定向 30%）", "85–136 发", "38.1%", "61.2%", "9 站"],
  ], [34, 16, 15, 17, 18]));
bodyChildren.push(body("政治拒止拒掉的是低价值盟友前沿站点——价值口径仅损失 0.2%，计数口径损失 13.4%：政治战咬掉的是存在感与前沿容量，而非资产重置价值。这解释了 P13 的核心发现（政治约束未击穿体系韧性），同时提示纯价值口径会低估政治战威力。"));
bodyChildren.push(h2("5.3 打掉 30% 节点的体系保留率（必答二）"));
bodyChildren.push(body("随机移除 30% 节点（k=20），体系价值保留率均值 70.1%（90% 区间 59.6%-80.0%）；按杀伤网 PAE 优先序定向移除 30%，保留率骤降至 28.8%——体系对随机毁伤存在大数冗余，对定向打点高度脆弱。定向曲线在移除 20%-30% 区间出现价值腰斩拐点，保护 Tier-1 枢纽是体系设计第一优先级。"));
bodyChildren.push(...figure("fig3_removal.png", "图 3：节点移除曲线（随机 vs 定向，阴影为随机 90% 区间）"));
bodyChildren.push(h2("5.4 敏感性参数排序（必答三）"));
bodyChildren.push(body("对五类参数做单因素扫描，按相对响应度（每单位参数的因变量相对变化，中位归一）排序：准入基线扰动 σ 居首（10.0），其后依次为拦截率水平（4.57）、定向移除规模 k（3.66）、主权打击强度（0.12）与 m(Denied) 政治先验（0.078）。结论：体系稳健性的主战场在不确定性管理，而非单点参数精调。"));
bodyChildren.push(...figure("fig4_sens.png", "图 4：敏感性参数响应度排序"));
bodyChildren.push(h2("5.5 交换比（必答四）"));
bodyChildren.push(body("防空拦截口径下，体系每放进一枚突防，红方付出 4.79 发（六策略区间 4.46-5.15，150 episodes 实测）；齐射场景红方 4 波 21 弹头对蓝方零战果（出动 156 架次全保存、损失率 0.0%）；对红方最有利的动能定向口径为 100-160 发换 20 座基地。三类交换比口径必须分开陈述，混用即误导。"));
bodyChildren.push(...figure("fig6_exchange.png", "图 5：六策略交换比对比"));
bodyChildren.push(h2("5.6 政治约束与体系韧性的成立边界（必答五）"));
bodyChildren.push(body("政治约束未击穿体系韧性，但韧性来自重构适应而非不受影响，结论有可复算的成立边界：10,000 次准入扰动下可用率均值 99.78%、最低 95.52%；置信层对 m(Denied) 先验单参数扰动稳健（0.10→0.40 时 Bel(Open) 仅从 0.7784 降至 0.7600，判决不翻转），冲突系数 K 从 0.075 线性升至 0.300 逼近 0.7 拒合成阈；真正的翻转机制在推理层——单基地状态断言改写即可由 HermiT 推理机自动重分类（Misawa 翻转测试，LaunchCapable 67→66）。"));
bodyChildren.push(...figure("fig5_mdenied.png", "图 6：m(Denied) 翻转边界扫描（D-S 置信层独立复算）"));

/* 第 6 章 */
bodyChildren.push(h1("六、本体语义层与知识工程"));
bodyChildren.push(h2("6.1 TO 五元组本体与机器校验"));
bodyChildren.push(body("目标特性本体（T1）以 OWL 2 DL 表达：67 个基地实体按四子类互斥分类，16 条跑道与 3 类准入状态共 86 实体；类定义公理 AirBase ≡ ∃hasPart.Runway 与 LaunchCapable ≡ ∃hasAccessState.(Open ⊔ Restricted) 驱动自动归类。机器校验三层：HermiT 描述逻辑一致性证明（翻转测试实测）；pySHACL 正负样本双向校验（负样本三注入：删军种码、纬度 999、缺状态断言，全部报警命中）；D-S 证据理论置信合成（精度分级 mass 与准入类型 mass 的 Dempster 组合，冲突系数 K<0.08 零拒绝）。全部断言接入 PROV-O 溯源图 643 三元组，逐断言回指权威源。"));
bodyChildren.push(...figure("fig7_bel.png", "图 7：67 基地 Bel(Open) 置信分布（按精度分级着色）"));
bodyChildren.push(h2("6.2 语义工具层与本体工作台"));
bodyChildren.push(body("语义工具层（P17）提供 browse / resolve / manifest 三个只读函数：四类语义对象 term 85 / mapping 16 / constraint 3 / evidence 71 可子串检索，个体全档案含类型、属性、适用约束、Bel/Pl 区间与证据源。提示词只注入 manifest 轻量清单，其余语义按需检索。本体工作台页面将类层级树、检索台、置信分布与决策链路审计聚合为单文件自包含页（111KB，断网可用），对标商业本体平台的画布交互范式。"));

/* 第 7 章 */
bodyChildren.push(h1("七、工程实现与质量保障"));
bodyChildren.push(h2("7.1 开发过程与规模"));
bodyChildren.push(body("系统自 2026-09-05 启动，32 天内完成 157 次提交（git log 实测），P1 至 P18 十八个阶段逐日留痕。全部产物由脚本链生成：删掉输出目录重跑仍能得到一致结果。"));
bodyChildren.push(...figure("fig8_commits.png", "图 8：开发提交时间线（git log 实测）"));
bodyChildren.push(h2("7.2 质量门禁与负载实测"));
bodyChildren.push(...dataTable("表 5：工程质量指标汇总",
  ["维度", "指标", "实测值"],
  [
    ["测试", "测试文件 / 断言", "26 个测试文件；本体 21 + DoDAF 26 + 语义工具 15 + 五问 20 + Web 认证 26 等纳入 CI 门禁"],
    ["CI/CD", "GitHub Actions 阶段", "Lint → Unit → Docker Build → Security → Push 全绿（Run 37413697749 等）"],
    ["负载", "SQLite WAL / gRPC / 引擎并发", "58,228 wps / 188.6 RPS（全级别 errors=0）/ 386.6 QPS"],
    ["内存治理", "2GB ECS 长时推演", "快照限长 240 条 + compose mem_limit 固化，RSS 平台期"],
    ["坐标防护", "引擎统一出口 _coord_check", "经度归一化 [-180,180)，6000 仿真秒 0 误拒 0 越界"],
    ["安全", "会话与接口", "JWT + 三级 RBAC + auth_request 门禁；口令摘要不落盘"],
  ], [14, 28, 58]));
bodyChildren.push(body("第三方可接入性以独立进程自测脚本实证：以第三方身份（仅走公开通道）完成登录、状态拉取、坐标独立复核、WS 订阅、分析触发与孪生注册全链路，带门禁引擎上 14/14 通过，证据文件随交付包提供。"));

/* 第 8 章 */
bodyChildren.push(h1("八、部署方案与运维"));
bodyChildren.push(...dataTable("表 6：部署架构与运维要点",
  ["项", "方案", "要点"],
  [
    ["部署形态", "阿里云 ECS 2GB + Docker Compose 双容器", "引擎容器（mem_limit 1200m）+ 展示中心 nginx"],
    ["入口", "8888 演示中心 / 8080 REST / 8765 WebSocket", "nginx auth_request 会话门禁，同源 /api 与 /ws 反代"],
    ["离线自包含", "2250 张印太瓦片入卷 + 浏览器端天文计算夜半球", "零外部数据源，断网可用"],
    ["复现包", "一键复现脚本 + 端到端日志样例", "依赖体检→口径自检→数据字典再生→五问实跑→验收测试，全绿实录入包"],
    ["安全网", "每 4 小时定时重启引擎", "内存护栏；重启窗口内 REST 短暂不可达属预期"],
  ], [14, 40, 46]));
bodyChildren.push(body("演示视频 V3（314 秒）由渲染管线全自动生成：神经旁白、词级同步字幕、程序化配乐，画面 100% 来自运行中的公网系统，含失效沙盘、政治拒止边界、参谋官降级与断网离线四个失败与边界段落；页面更新后重跑脚本即可再生，属可持续产能而非一次性手工作品。"));

/* 第 9 章 */
bodyChildren.push(h1("九、风险分析与演进路线"));
bodyChildren.push(...dataTable("表 7：风险与演进路线",
  ["项", "现状与风险", "缓解 / 路线"],
  [
    ["本体演化闭环", "演化机制（轨迹诊断→归因→类型化补丁→配对评估门禁）已立项未开跑", "P17 计划赛后启动；当前以「发布即冻结、机器可校验」口径如实陈述，未做不说做完"],
    ["多模型网关", "LLM 参谋官单模型直连", "语义层保持模型无关；网关化改造列为赛后"],
    ["观测维度锚定", "DQN 观测与 22 站推演口径绑定，67 站需重训", "口径权威表显式区分；67 站负载已全绿验证（58,228 wps）"],
    ["跨引擎校准样本", "Brier 分数基于 35 个单场景判定样本", "同步层持续累积跨场景在线校准计数，诚实口径优先"],
  ], [16, 40, 44]));
bodyChildren.push(body("演进路线遵循最小完备性红线：本体宁小勿大，堆砌扣分；权威本体保持模型无关、标准格式（OWL 2 DL / Turtle），可导入任意第三方本体平台。"));

/* 第 10 章 */
bodyChildren.push(h1("十、结论"));
bodyChildren.push(body("PMTEC 系统在 32 天内完成了从权威数据底座、政治准入状态机、深度强化学习决策到本体语义层的全链路数字孪生体系构建，并以机器可校验的方式回答了五个必答问题：失效场景分级可量化（政治拒止 0 弹咬掉前沿存在感，定向 30% 打击价值保留率 28.8% 且有 5.04 发/突防的代价交叉验证）；敏感性排序明确（不确定性强度居首）；交换比三类口径分列；政治韧性的独立判断成立且有可复算边界。工程侧 157 次提交、26 个测试文件、CI 六阶段全绿与第三方接入自测 14/14，构成可复现、可审计、可交付的完整证据链。适应优于压制——用真实世界数据让数字孪生更真，用政治不确定性让对抗更聪明。"));

/* ══════════ 文档组装 ══════════ */
const pgSize = { width: 11906, height: 16838 };
const pgMargin = { top: 1440, bottom: 1440, left: 1701, right: 1417 };

const doc = new Document({
  styles: {
    default: {
      document: {
        run: { font: { eastAsia: "SimSun", ascii: "Times New Roman" }, size: 24, color: BODY },
        paragraph: { spacing: { line: 312 } },
      },
      heading1: {
        run: { font: { eastAsia: "SimHei", ascii: "Times New Roman" }, size: 32, bold: true, color: INK },
        paragraph: { spacing: { before: 360, after: 160, line: 312 }, outlineLevel: 0 },
      },
      heading2: {
        run: { font: { eastAsia: "SimHei", ascii: "Times New Roman" }, size: 28, bold: true, color: INK },
        paragraph: { spacing: { before: 240, after: 120, line: 312 }, outlineLevel: 1 },
      },
      heading3: {
        run: { font: { eastAsia: "SimHei", ascii: "Times New Roman" }, size: 24, bold: true, color: INK },
        paragraph: { spacing: { before: 200, after: 100, line: 312 }, outlineLevel: 2 },
      },
    },
  },
  sections: [
    /* 封面 */
    {
      properties: { page: { size: pgSize, margin: { top: 0, bottom: 0, left: 0, right: 0 } } },
      children: buildCoverR4({
        title: "PMTEC 数字孪生战场系统技术方案",
        titleLinesOverride: ["PMTEC 数字孪生战场", "系统技术方案"],
        englishLabel: "TECHNICAL PROPOSAL",
        subtitle: "盟友基地体系政治韧性数字孪生 · DTC2026 赛道二",
        metaLines: [
          "文档版本：V3.0（P18 评审整改后）",
          "编制单位：根深叶茂团队",
          "编制日期：2026 年 10 月",
          "信息截至：2026-09（CRS R47589 / DoD FY2024 BSR）",
        ],
        footerLeft: "根深叶茂团队",
        footerRight: "PMTEC · DTC2026",
      }),
    },
    /* 前置：摘要 + 目录（Roman） */
    {
      properties: {
        type: SectionType.NEXT_PAGE,
        page: { size: pgSize, margin: pgMargin,
          pageNumbers: { start: 1, formatType: NumberFormat.UPPER_ROMAN } },
      },
      headers: { default: pageHeader() },
      footers: { default: pageFooter() },
      children: [
        h1("摘  要"),
        body("本方案阐述 PMTEC 数字孪生战场系统的总体设计、关键机制与量化验证。系统面向印太战区盟友基地体系，将政治准入建模为仿真状态机并纳入 ASDA 闭环，构建了从 67 实体权威数据底座（逐字段溯源 CRS 与国防部 FY2024 报告）、深度强化学习决策（219 维观测）到 OWL 2 DL 本体语义层（HermiT 推理、SHACL 双向校验、D-S 置信、PROV-O 溯源）的完整体系。"),
        body("量化验证：三场景拦截率对照 76.2%→79.0%→79.1%（政治约束引入后不降反稳），概率校准 Brier 分数 0.1128，十万次敏感性采样最差可用率 95.5%；必答五问全部实跑作答——定向打掉 30% 节点体系价值保留率 28.8%（红方代价 100-160 发），敏感性排序以政治不确定性强度居首，交换比 4.79 发/突防。工程侧 157 次提交、26 个测试文件、CI 六阶段全绿、第三方接入自测 14/14、演示中心公网部署断网可用。"),
        new Paragraph({
          alignment: AlignmentType.JUSTIFIED,
          indent: { firstLine: 480 },
          spacing: { line: 312 },
          children: [bt("本方案的全部数字均可由仓库脚本一键复现，复现方法与端到端日志样例随交付包提供。"), new PageBreak()],
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { before: 480, after: 360 },
          children: [new TextRun({ text: "目  录", bold: true, size: 32,
            font: { eastAsia: "SimHei", ascii: "Times New Roman" }, color: INK })],
        }),
        new TableOfContents("目录", { hyperlink: true, headingStyleRange: "1-2" }),
        new Paragraph({
          spacing: { before: 200 },
          children: [new TextRun({
            text: "注：本目录由域代码生成。文档编辑后如需刷新页码，请在目录上右键选择「更新域 → 更新整个目录」。",
            italics: true, size: 18, color: "888888",
            font: { eastAsia: "SimSun" } })],
        }),
      ],
    },
    /* 正文（Arabic 从 1 起） */
    {
      properties: {
        type: SectionType.NEXT_PAGE,
        page: { size: pgSize, margin: pgMargin,
          pageNumbers: { start: 1, formatType: NumberFormat.DECIMAL } },
      },
      headers: { default: pageHeader() },
      footers: { default: pageFooter() },
      children: bodyChildren,
    },
  ],
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync(OUT, buf);
  console.log("生成完成:", OUT, (buf.length / 1024).toFixed(0) + "KB");
});
