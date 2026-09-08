import type { CampusPhoto, Experience, Honor, Project, Skill } from '../types';

// 个人资料修改入口：姓名、简介、联系方式、技能、项目、经历和荣誉均集中在此文件。
export const siteData = {
  name: '张航铭',
  initials: 'ZHM',
  identity: '机器人工程专业本科生 · 机器人、嵌入式与人工智能方向学习者',
  major: '机器人工程',
  intro: '关注机器人感知、定位导航、嵌入式开发、计算机视觉和智能硬件，希望通过技术解决真实问题。',
  location: '重庆 · 重庆大学',
  email: '2361312720@qq.com',
  github: 'https://github.com/zhanghangming-gif/personal_site',
  resume: '/resume.docx',
  learning: ['硬件设计', 'ROS2 导航', '智能硬件产品开发'],
  about: {
    direction: '我希望理解机器人如何感知、决策与行动，也重视它为什么被需要。以第一性原理拆解问题，以产品思维关注用户痛点，再用工程实践把想法转化为可靠、可验证的系统。',
    focus: '关注机器人在真实场景中的感知、定位、导航与人机交互，以及复杂技术如何被组织成清晰、稳定、易用的产品体验。',
    purpose: '希望做出不是为了展示技术而存在，而是真正回应用户痛点、能够持续创造价值的机器人与智能产品。',
    character: '认真负责、执行力强，喜欢在团队协作中主动承担问题，也愿意持续复盘。',
    interests: '技术之外长期参与学生艺术团的排练与演出，在单簧管演奏、舞台实践和团队协作中保持对音乐的热爱。',
  },
};

export const skills: Skill[] = [
  { name: 'C/C++', category: '编程语言', level: '熟悉' },
  { name: 'Python', category: '编程语言', level: '熟悉' },
  { name: 'STM32', category: '嵌入式开发', level: '熟悉' },
  { name: 'ESP32', category: '嵌入式开发', level: '熟悉' },
  { name: 'ROS2', category: '机器人与ROS', level: '正在学习' },
  { name: 'FAST-LIO2', category: '机器人与ROS', level: '使用过' },
  { name: 'Nav2', category: '机器人与ROS', level: '正在学习' },
  { name: '激光雷达', category: '机器人与ROS', level: '使用过' },
  { name: 'YOLO', category: '计算机视觉', level: '使用过' },
  { name: 'OpenCV', category: '计算机视觉', level: '使用过' },
  { name: 'Linux', category: '工具与平台', level: '熟悉' },
  { name: 'Git', category: '工具与平台', level: '使用过' },
  { name: 'Docker', category: '工具与平台', level: '正在学习' },
  { name: 'PCB设计', category: '硬件设计', level: '正在学习' },
  { name: '前端基础', category: '工具与平台', level: '使用过' },
];

export const projects: Project[] = [
  {
    id: 'smart-road-cone',
    title: '智能车载应急路锥',
    type: '智能硬件',
    summary:
      '面向高速公路、夜间停车与恶劣天气等路侧应急场景，设计可由车内远程布设的智能警示设备，让警示先到达危险现场，让人员尽量留在安全区域。',
    role: '参与系统方案设计、嵌入式控制、交互原型与整机联调',
    tech: ['ESP32-S3', 'BLE / WiFi', 'GPS / IMU', '超声波', 'WS2812'],
    status: '已完成原型与用户验证',
    featured: true,
    cover: '/projects/smart-road-cone/prototype.webp',
    background:
      '传统三角警示牌需要驾驶员下车并步行至车后布设，在高速车流、雨雾、夜间或道路应急环境中存在二次事故风险；同时，传统警示牌可见性有限，也缺少设备状态反馈。',
    goal: '将“人去布设危险警示”转化为“设备代替人完成危险布设”，通过远程控制、多通道警示和实时状态回传，降低人员暴露时间与操作负担。',
    solution:
      '以 ESP32-S3 为主控，利用 BLE GATT 与 WiFi SoftAP 连接手机小程序；融合 GPS、超声波、IMU 与电池数据，驱动底盘、灯光和语音模块，实现远程移动、避障、定位、声光警示、安全监测及状态反馈。',
    architecture: [
      '手机小程序',
      'BLE / WiFi 通信',
      'ESP32-S3 主控',
      '多传感器感知',
      '移动底盘与执行器',
      '声光警示与状态回传',
    ],
    workflow: ['发现车辆故障', '车内连接设备', '远程布设路锥', '开启声光警示', '查看状态并等待救援'],
    challenge:
      '系统既要在复杂路面与弱光环境中保持通信和移动可靠性，也要把连接、控制、警示切换与异常处理压缩成低学习成本的交互流程，并确保失联时能够安全停车。',
    result:
      '完成可移动实物原型与小程序交互验证。6 名目标用户测试中，平均完成时间 72 秒、任务成功率 83%、平均错误 1.2 次/人、平均提示 0.8 次/人；主观易用性评分 4.1/5，安全感评分 4.4/5。',
    photos: [
      {
        src: '/projects/smart-road-cone/prototype.webp',
        alt: '智能车载应急路锥实物原型',
        caption: '可折叠三角警示结构与移动底盘结合，通过高亮灯带提升夜间和恶劣天气下的可见性。',
      },
      {
        src: '/projects/smart-road-cone/exhibition.webp',
        alt: '智能车载应急路锥项目现场展示',
        caption: '项目现场展示包含实物原型、手机端操作说明和以人为中心的系统设计海报。',
      },
      {
        src: '/projects/smart-road-cone/poster.webp',
        alt: '智能车载应急路锥完整设计海报',
        caption: '海报梳理了用户洞察、系统架构、数据闭环、用户测试结果与未来拓展方向。',
        contain: true,
      },
    ],
  },
  {
    id: 'robocon-vision',
    title: 'ROBOCON 机器人视觉与感知系统',
    type: '机器人视觉',
    summary:
      '识别赛场物资箱的颜色与物资类别，同时解析数字和运算符组成的算术题；根据计算结果建立目标映射，为机器人输出应抓取的物资箱颜色与编号。',
    role: '物资箱检测、算术表达式识别、决策逻辑与整机通信联调',
    tech: ['YOLO', 'OpenCV', 'Python', '目标检测', '决策映射'],
    status: '持续迭代',
    featured: true,
    cover: '/projects/robocon-vision/decision-pipeline.webp',
    background:
      '赛场中分布着不同颜色和类别的物资箱，机器人需要先读取现场算术题，再根据运算结果确定目标颜色，最终从多个候选物资箱中选择正确目标。视觉模块必须把“看见目标”进一步转化为可供主控直接使用的抓取决策。',
    goal: '建立从物资箱颜色与类别检测、数字和运算符识别、表达式求值到目标箱映射的完整视觉决策链路，稳定输出机器人应抓取的颜色和物资箱编号。',
    solution:
      '使用 YOLO 分别检测物资箱特征、数字和加减乘除符号；对表达式区域进行排序与稳定性跟踪，完成算术求值后按比赛规则进行映射，再结合物资箱识别结果生成抓取目标，并通过通信接口发送给机器人主控。',
    architecture: [
      '相机图像采集',
      '物资箱颜色与类别检测',
      '数字与运算符识别',
      '表达式求值与规则映射',
      '目标箱筛选',
      '主控抓取决策',
    ],
    workflow: [
      '采集并标注赛场数据',
      '训练物资箱与字符模型',
      '识别并解析算术题',
      '映射目标颜色与编号',
      '联调整机抓取流程',
    ],
    challenge:
      '赛场光照、视角、遮挡和运动模糊会影响物资箱与字符识别；算术题还要求字符顺序正确、结果连续稳定，并与物资箱编号和主控动作时序准确对应。',
    result:
      '完成物资箱颜色与类别检测、算术表达式识别和决策映射原型，能够根据运算结果输出目标物资类型及候选箱编号，为机器人自动选择和抓取正确物资箱提供决策依据。',
    galleryTitle: '从视觉识别到抓取决策',
    galleryDescription:
      '四组画面记录视觉系统在真实赛场环境中的完整工作链路：先检测物资箱的颜色与类别，再识别数字和运算符、计算算术题结果，最后依据比赛规则筛选目标颜色与物资箱编号，为机器人抓取动作提供决策。',
    photos: [
      {
        src: '/projects/robocon-vision/material-detection-overview.webp',
        alt: 'YOLO 对赛场多种物资箱进行检测',
        caption:
          '在赛场环境中同时定位并识别食品、药品、工具和仪器等物资箱，为后续颜色与目标筛选提供候选集合。',
      },
      {
        src: '/projects/robocon-vision/colored-box-detection.webp',
        alt: '视觉系统识别不同颜色和类别的物资箱',
        caption: '面对不同距离、角度与遮挡情况，视觉模块持续输出物资箱类别、位置和置信度。',
      },
      {
        src: '/projects/robocon-vision/expression-recognition.webp',
        alt: '视觉系统识别数字和算术运算符并计算结果',
        caption: '检测数字与除号、减号等运算符，按照空间顺序重建表达式并计算结果。',
      },
      {
        src: '/projects/robocon-vision/decision-pipeline.webp',
        alt: '物资箱识别、算术题求值与抓取决策联合调试界面',
        caption: '将表达式结果映射到目标类别，再结合物资箱编号生成抓取决策，打通视觉感知到主控执行的链路。',
      },
    ],
  },
  {
    id: 'lidar-navigation',
    title: '激光雷达建图、定位与导航',
    type: '定位导航',
    summary:
      '基于宇树 L2 激光雷达搭建从 FAST-LIO2 三维建图、FAST-LIO2 Localization＋ICP 定位，到 Nav2 路径规划与实机导航验证的完整自主移动链路。',
    role: '建图与定位算法部署、ROS2 接口适配、Nav2 集成及实机调试',
    tech: ['ROS2', '宇树 L2', 'FAST-LIO2', 'FAST-LIO2 Localization', 'ICP', 'Nav2'],
    status: '已完成实机验证',
    cover: '/projects/lidar-navigation/nav2-localization.webp',
    featured: true,
    background:
      '移动机器人在复杂室内环境中自主运行，需要同时解决高质量地图构建、稳定重定位、路径规划和底盘执行。单个算法能够运行并不等于系统可用，点云、位姿、二维代价地图和控制链路必须在统一坐标系与时间基准下协同。',
    goal: '以宇树 L2 激光雷达为主要感知设备，构建可重复运行的“建图—定位—规划—控制”流程，并在真实机器人平台上验证定位稳定性与 Nav2 自主导航能力。',
    solution:
      '建图阶段使用 FAST-LIO2 融合 L2 点云与 IMU 数据生成三维点云地图；定位阶段通过 FAST-LIO2 Localization 结合 ICP 完成当前扫描与先验地图配准，持续输出机器人位姿；导航阶段将定位结果、静态地图和传感器数据接入 Nav2，完成全局/局部路径规划、避障与速度控制。',
    architecture: ['宇树 L2＋IMU', 'FAST-LIO2 建图', 'Localization＋ICP', 'Nav2 规划', '实机底盘'],
    workflow: ['雷达与坐标系配置', 'FAST-LIO2 三维建图', '地图处理与加载', 'ICP 定位验证', 'Nav2 实机导航'],
    challenge:
      '系统集成的难点集中在雷达与底盘坐标外参、ROS2 TF 树、点云与里程计时间同步，以及三维定位结果向 Nav2 二维导航坐标系的稳定传递。通过统一 frame 命名、检查时间戳与变换链，并反复对比当前扫描和先验地图的重合程度完成调试。',
    result:
      '完成室内场景三维点云建图，实现 FAST-LIO2 Localization＋ICP 的先验地图定位；在 Nav2 中打通地图、定位、路径规划和底盘控制，并完成真实机器人自主导航验证。',
    galleryTitle: '从三维建图到自主导航',
    galleryDescription:
      '五组画面依次呈现 FAST-LIO2 三维建图、先验地图定位、Nav2 路径规划与导航验证，展示整套系统从点云感知到机器人执行的完整链路。',
    photos: [
      {
        src: '/projects/lidar-navigation/fastlio-map-green.webp',
        alt: 'FAST-LIO2 使用宇树 L2 激光雷达构建室内三维点云地图',
        caption:
          '使用宇树 L2 激光雷达与 IMU 数据运行 FAST-LIO2，重建实验场地、墙面和设施结构的三维点云地图。',
        contain: true,
      },
      {
        src: '/projects/lidar-navigation/fastlio-map-color.webp',
        alt: 'FAST-LIO2 构建的彩色高度三维点云地图',
        caption: '按高度着色的点云结果用于检查地图结构、层次关系和轨迹连续性，为后续先验地图定位提供基础。',
        contain: true,
      },
      {
        src: '/projects/lidar-navigation/nav2-localization.webp',
        alt: 'FAST-LIO2 Localization 与 Nav2 静态地图联合调试界面',
        caption: '左侧验证当前扫描与先验点云地图的定位状态，右侧将位姿接入 Nav2 静态地图与规划链路。',
        contain: true,
      },
      {
        src: '/projects/lidar-navigation/nav2-path.webp',
        alt: 'Nav2 路径规划与 FAST-LIO2 Localization 运行画面',
        caption: 'Nav2 输出全局与局部路径，定位模块持续提供机器人位姿，在真实场地中完成导航闭环。',
        contain: true,
      },
      {
        src: '/projects/lidar-navigation/icp-localization.webp',
        alt: 'ICP 当前点云与先验地图配准定位画面',
        caption:
          '通过 FAST-LIO2 Localization 与 ICP 将当前扫描配准到先验地图；红、黄点云的重合状态直观反映定位效果。',
        contain: true,
      },
    ],
    videos: [
      {
        src: '/projects/lidar-navigation/robot-nav2-demo.mp4',
        title: 'Nav2 实机导航验证',
        caption: '将定位、地图、全局/局部规划与底盘控制部署到真实机器人，完成目标点导航与现场验证。',
        poster: '/projects/lidar-navigation/nav2-path.webp',
      },
    ],
  },
  {
    id: 'five-bar-robot',
    title: '并联五连杆轮腿机器人',
    type: '机器人控制',
    summary:
      '围绕并联五连杆轮腿机器人完成机械结构设计、手机端 BLE 遥控器，以及 ESP32-S3＋OV2640 摄像头图传与网页上位机开发，打通远程操控和第一视角观察链路。',
    role: '机械结构设计、BLE 遥控器、摄像头图传与网页上位机开发、整机联调',
    tech: ['机械设计', 'Fusion 360', 'ESP32-S3', 'BLE', 'OV2640', 'Web'],
    status: '已完成整机验证',
    cover: '/projects/five-bar-robot/robot-prototype.webp',
    featured: true,
    background:
      '并联五连杆轮腿机构兼具轮式移动效率与腿式姿态调节能力，但机械连杆、驱动器和电控板需要在有限空间内可靠装配；机器人远程运行时，还需要低延迟控制入口与第一视角画面，帮助操作者判断环境和机器人状态。',
    goal: '完成轮腿机构与电控安装结构设计，建立安全、直观的无线遥控方式，并将摄像头画面稳定传输到网页上位机，使机器人能够在离开操作者视线时继续完成观察、控制和调试。',
    solution:
      '机械部分使用三维建模完成并联五连杆、轮组、驱动器安装与双层电控板布局；遥控部分通过手机端 BLE 界面连接机器人控制器，将虚拟摇杆转换为线速度 Vx 与角速度 Vw，并提供急停、速度上限、平衡和 LQR 模式开关；图传部分使用 ESP32-S3 驱动 OV2640，通过网页上位机显示实时画面，并开放分辨率、画质、亮度、对比度、饱和度及画面翻转等参数调节。',
    architecture: [
      '并联五连杆机械结构',
      '机器人底层控制',
      'ESP32-S3 通信',
      '手机 BLE 遥控器',
      'OV2640 图传上位机',
    ],
    workflow: ['机械结构建模', '板件与电控布局', 'BLE 控制界面开发', '摄像头与网页图传', '整机遥控验证'],
    challenge:
      '项目需要同时处理机构运动空间、零部件干涉、电控安装与线束布局；控制端则要避免蓝牙断连、摇杆误触和异常指令带来的风险，并在有限带宽下平衡图传清晰度、帧率和操控实时性。',
    result:
      '完成并联五连杆轮腿结构与整机装配方案，实现具备急停、速度限制和控制模式切换的 BLE 遥控器；完成 ESP32-S3＋OV2640 实时图传及网页参数调节，并在实机上完成远程操控与画面回传验证。',
    galleryTitle: '从机械结构到远程操控',
    galleryDescription:
      '五组画面呈现机器人从并联五连杆机械建模、整机装配，到手机 BLE 遥控和摄像头图传上位机的完整开发过程，展示机械、嵌入式通信与交互界面的协同落地。',
    photos: [
      {
        src: '/projects/five-bar-robot/robot-prototype.webp',
        alt: '并联五连杆轮腿机器人实机与摄像头模块',
        caption: '完成轮腿机器人整机装配，并将摄像头、电控板、急停开关和线束集成到有限机身空间中。',
      },
      {
        src: '/projects/five-bar-robot/mechanical-assembly.webp',
        alt: '并联五连杆轮腿机器人完整机械与电控布局三维模型',
        caption: '完整装配模型用于检查连杆运动范围、驱动器安装、双层电控板布局和结构干涉。',
        contain: true,
      },
      {
        src: '/projects/five-bar-robot/mechanical-chassis.webp',
        alt: '并联五连杆轮腿机器人底盘机械结构三维模型',
        caption: '围绕并联五连杆与轮组设计底盘结构，在尺寸、强度、装配空间和可加工性之间进行权衡。',
        contain: true,
      },
      {
        src: '/projects/five-bar-robot/ble-controller.webp',
        alt: '并联五连杆轮腿机器人手机 BLE 遥控器界面',
        caption: '手机端 BLE 遥控器提供虚拟摇杆、线速度与角速度显示、急停、速度上限及平衡/LQR 模式切换。',
        contain: true,
      },
      {
        src: '/projects/five-bar-robot/camera-stream.webp',
        alt: 'ESP32-S3 OV2640 摄像头实时图传网页上位机',
        caption: '网页上位机实时显示 OV2640 画面，并支持画质、亮度、对比度、饱和度和翻转等参数调节。',
        contain: true,
      },
    ],
    videos: [
      {
        src: '/projects/five-bar-robot/control-camera-demo.mp4',
        title: '遥控、图传与整机联调演示',
        caption: '记录手机遥控、机器人运动和摄像头画面回传的实机验证过程。',
        poster: '/projects/five-bar-robot/robot-prototype.webp',
      },
    ],
  },
  {
    id: 'stirling-engine',
    title: '斯特林发动机制作',
    type: '机械设计',
    summary: '完成从三维建模、ADAMS 机构仿真到加工装配和热驱动实物验证的完整工程实践。',
    role: '机械结构建模、ADAMS 仿真、加工装配与运行调试',
    tech: ['Fusion 360', 'ADAMS', '机械设计', '机构仿真', '加工装配'],
    status: '已完成实物验证',
    cover: '/projects/stirling-engine/stirling-prototype.webp',
    featured: true,
    background:
      '斯特林发动机依靠外部热源形成温差，使密闭工质周期性膨胀与压缩，再由活塞、曲柄连杆和飞轮将热能转化为连续机械运动。小型原型对配合间隙、密封性能、轴系对中和机构相位尤为敏感。',
    goal: '设计并制作一台桌面型斯特林发动机，通过三维装配与动力学仿真验证机构可行性，并在外部加热条件下实现实物持续运行。',
    solution:
      '围绕气缸、活塞、曲柄连杆、飞轮、支架与底座完成三维结构设计；在 ADAMS 中建立运动副并检查活塞位移、相位关系、飞轮连续性与潜在干涉；随后完成零件加工、装配对中和低摩擦调试，通过调整热源位置、连接间隙与轴系阻力实现稳定运行。',
    architecture: ['热端与冷端', '位移活塞与动力活塞', '曲柄连杆机构', '飞轮', '底座与支架'],
    workflow: [
      '结构方案与尺寸设计',
      '三维建模与装配检查',
      'ADAMS 运动仿真',
      '加工装配与对中',
      '加热运行与调试',
    ],
    challenge:
      '需要同时处理气路密封、运动副摩擦、轴系同轴度、曲柄相位差与加热稳定性；任一环节偏差都可能造成启动力矩不足或运行中断。',
    result:
      '完成整机三维模型与 ADAMS 运动仿真，制作出可运行的斯特林发动机实物，并在外部热源驱动下实现飞轮连续转动，验证了设计、加工与装配方案。',
    galleryTitle: '从机构建模到热驱动运行',
    galleryDescription: '通过三维模型、实物原型与小组合照，记录结构设计、加工装配和运行验证的完整过程。',
    photos: [
      {
        src: '/projects/stirling-engine/stirling-model.webp',
        alt: '斯特林发动机三维结构建模图',
        caption:
          '在三维模型中完成气缸、活塞、曲柄连杆、飞轮及支撑结构的装配设计，并提前检查运动空间与零件干涉。',
        contain: true,
      },
      {
        src: '/projects/stirling-engine/stirling-prototype.webp',
        alt: '完成加工装配的斯特林发动机实物',
        caption: '完成零件加工与整机装配后，围绕轴系对中、机构摩擦、气路密封和热源位置进行多轮运行调试。',
        contain: true,
      },
      {
        src: '/projects/stirling-engine/stirling-team.webp',
        alt: '斯特林发动机项目小组成员合照',
        caption: '小组完成方案设计、建模仿真、加工装配与实物验证后的项目合照。',
      },
    ],
    videos: [
      {
        src: '/projects/stirling-engine/adams-simulation.mp4',
        title: 'ADAMS 机构运动仿真',
        caption:
          '在 ADAMS 中验证曲柄连杆运动、活塞往复位移、相位配合与飞轮连续转动，为零件加工和装配调试提供依据。',
        poster: '/projects/stirling-engine/stirling-model.webp',
      },
      {
        src: '/projects/stirling-engine/physical-operation.mp4',
        title: '斯特林发动机实物运行',
        caption: '外部热源建立温差后，实物飞轮能够持续转动，完成从虚拟仿真到真实机械运动的闭环验证。',
        poster: '/projects/stirling-engine/stirling-prototype.webp',
      },
    ],
  },
  {
    id: 'jumping-robot',
    title: '弹跳机器人的制作',
    type: '机器人设计与控制',
    summary: '围绕储能释放、动作时序与整机稳定性完成两版原型迭代，并最终实现机器人离地起跳。',
    role: '结构方案、驱动控制与整机联调',
    tech: ['机械结构', '电机驱动', '动作控制', '整机调试'],
    status: '已完成起跳验证',
    cover: '/projects/jumping-robot/final-version.webp',
    featured: true,
    background:
      '弹跳动作需要在很短时间内完成能量积累与快速释放，对结构刚度、驱动能力、重心位置、落地姿态和控制时序都有较高要求。第一版原型虽然能够执行动作，但能量利用和机构配合不足，未能成功离地。',
    goal: '制作一台能够自主完成蓄力、释放和离地动作的弹跳机器人，并通过两版实机迭代验证结构与控制方案。',
    solution:
      '以第一版测试为依据，分析未起跳的原因，围绕传动阻力、有效行程、能量释放速度、整机质量分布与动作时序进行调整；在最终版中重新匹配机构和驱动参数，并通过逐步提高输出的方式完成安全联调。',
    architecture: ['储能与释放机构', '驱动执行单元', '控制与动作时序', '机体结构', '供电与安全保护'],
    workflow: ['第一版原型制作', '未起跳问题分析', '结构与参数迭代', '低功率动作测试', '最终版起跳验证'],
    challenge:
      '第一版能够运动但没有获得足够的离地冲量，需要区分结构卡滞、能量损耗、输出时序和重心稳定性等多方面因素，并在保证安全的前提下反复验证。',
    result:
      '完成从失败原型到成功版本的迭代：第一版验证了基本动作链路但未能起跳，最终版通过结构和控制调整实现机器人明显离地，形成了完整的故障分析与实机优化经验。',
    galleryTitle: '从未起跳到成功离地',
    galleryDescription: '两段实机记录呈现第一版暴露问题、分析原因并完成最终版起跳验证的迭代过程。',
    videos: [
      {
        src: '/projects/jumping-robot/first-version.mp4',
        title: '第一版原型：完成动作但未能起跳',
        caption:
          '第一版已经能够执行蓄力与释放动作，但有效冲量不足，机器人未能离地。这次测试用于定位传动损耗、机构行程、输出时序与重心配置等问题。',
        poster: '/projects/jumping-robot/first-version.webp',
      },
      {
        src: '/projects/jumping-robot/final-version.mp4',
        title: '最终版：成功完成离地起跳',
        caption:
          '在调整机械结构、传动配合和动作时序后，最终版本获得了足够的瞬时输出，成功完成离地起跳，验证了迭代方案。',
        poster: '/projects/jumping-robot/final-version.webp',
      },
    ],
  },
  {
    id: 'math-modeling',
    title: '数学建模项目',
    type: '建模分析',
    summary:
      '围绕可持续月球基地的地月物流问题，对太空电梯、火箭与混合运输方案进行多阶段建模，在成本、时间、可靠性、水资源和环境影响之间寻找平衡。',
    role: '模型设计、计算与写作',
    tech: ['Python', 'AHP', '蒙特卡洛模拟', 'NSGA-II', '多目标优化'],
    status: '已完成',
    cover: '/projects/math-modeling/mcm-honorable-mention.webp',
    coverContain: true,
    featured: true,
    background:
      '建立长期月球基地需要持续运输基础设施、物资与水资源。太空电梯和传统火箭在建设周期、运输成本、故障风险与环境代价上各有差异，单一指标无法直接给出最优方案。',
    goal: '建立一个能够比较纯太空电梯、纯火箭和混合运输方案的多阶段模型，并在系统异常、水资源供给和环境约束下给出兼顾经济性、鲁棒性与可持续性的地月物流策略。',
    solution:
      '首先构建确定性物流动力学与加权总成本模型，并通过 AHP 综合时间和成本；随后使用蒙特卡洛模拟评估缆绳不稳定、火箭失败和电梯停机等随机风险；在资源层面引入 BLSS 水需求与 ISRU 动态部署模型；最后构建环境损害指数，并使用 NSGA-II 搜索时间、成本和环境影响之间的 Pareto 最优解。',
    architecture: ['物流方案定义', 'AHP 综合评价', '蒙特卡洛风险仿真', '水资源与 ISRU', 'NSGA-II 多目标优化'],
    workflow: [
      '拆解地月物流问题',
      '建立确定性模型',
      '加入随机故障情景',
      '分析资源与环境影响',
      '敏感性分析与论文写作',
    ],
    challenge:
      '问题跨越运输、风险、生命保障和环境评价多个层次，需要在有限竞赛时间内统一量纲、确定合理权重，并控制模型复杂度，使结果既可计算又具有清晰解释。',
    result:
      '完成《Optimizing Earth-Moon Logistics: A Multi-Stage Approach for a Sustainable Lunar Colony》建模论文，形成兼顾成本效益、系统鲁棒性与可持续性的决策框架，并获得 2026 年美国大学生数学建模竞赛 Honorable Mention（H 奖）。',
  },
];

export const experiences: Experience[] = [
  {
    id: 'bashu',
    period: '2021.09 — 2024.06',
    organization: '巴蜀中学',
    role: '高中阶段',
    work: '在巴蜀中学完成高中阶段学习，在扎实的课程训练之外，也积极参与班级建设、校园运动会与集体活动。三年的学习与生活让我逐步形成稳定的学习节奏，并学会在压力与目标之间保持专注。',
    growth:
      '在同伴、师长与家人的陪伴中，我建立起自我管理、持续投入和主动承担的习惯；这段经历也为进入大学后探索工程、机器人与艺术方向奠定了底色。',
  },
  {
    id: 'mingyue',
    period: '2024.09 — 至今',
    organization: '重庆大学 · 明月科创实验班',
    role: '国家卓越工程师学院 · 机器人工程专业本科生',
    work: '就读于重庆大学国家卓越工程师学院明月科创实验班，专业为机器人工程。学院是全国首批国家卓越工程师学院建设试点单位之一；明月班是重庆大学推进新工科教育改革的“实验田”，打破传统学科边界，以跨学科课程、探究式教学和项目驱动培养设计思维、工程思维与系统思维。',
    growth:
      '围绕工程原理、程序设计、嵌入式系统、控制算法与机器人基础开展学习和项目实践，并通过科创训练营、机器人竞赛、产业参访和国际交流，在开放问题中主动拆解目标、制作原型、验证方案并持续复盘。',
  },
  {
    id: 'gsing',
    period: '2024 — 至今',
    organization: 'GSing战队',
    role: '也是一名 RCer · 视觉组成员',
    work: '作为战队视觉组成员，参与机器人视觉感知、目标识别、通信联调与赛场测试；在长期备赛中围绕真实任务反复采集数据、验证方案、定位问题，并与机械、电控及其他算法成员协同推进整机落地。',
    growth:
      '从让代码在电脑上运行，到让整套系统在赛场中稳定执行，我逐渐建立起面向真实约束解决问题的工程思维，也更理解责任、沟通和团队协作对于竞赛机器人的意义。',
  },
  {
    id: 'art',
    period: '2024.09 — 至今',
    organization: '重庆大学学生艺术团',
    role: '单簧管首席 · 交响乐队副队长',
    work: '担任学生艺术团管乐队、交响乐队单簧管演奏员及重庆大学单簧管首席；担任重庆大学 2025—2026 学年交响乐队副队长，参与日常排练、专场音乐会与校园艺术活动，并作为副队长参与组织重庆大学 2026 年毕业音乐会，协助推进排练统筹、成员沟通和演出执行。',
    growth:
      '在持续的舞台实践中磨炼演奏能力与审美表达，也在组织协调中学会倾听、担当与团队协作，让理性工程思维与感性艺术体验彼此滋养。',
  },
];

export const bashuPhotos: CampusPhoto[] = [
  {
    src: '/bashu/sports-day.webp',
    alt: '巴蜀中学校园运动会班级同学合影',
    caption: '在运动会与班级活动中并肩投入，留下属于集体的热烈记忆。',
  },
  {
    src: '/bashu/class-group.webp',
    alt: '巴蜀中学班级同学在校园合影',
    caption: '三年朝夕相处，在共同学习、讨论与成长中建立珍贵的同窗情谊。',
  },
  {
    src: '/bashu/graduation-family.webp',
    alt: '高中毕业时与家人在巴蜀中学校园合影',
    caption: '毕业时刻与家人合影，感谢一路以来的支持、理解与陪伴。',
  },
  {
    src: '/bashu/campus-motto.webp',
    alt: '巴蜀中学校园内悬挂的毕业寄语',
    caption: '校园里的毕业寄语，为高中阶段画下句点，也提醒我带着自信继续出发。',
  },
];

export const mingyuePhotos: CampusPhoto[] = [
  {
    src: '/mingyue/summer-camp-2025.jpg',
    alt: '2025年重庆大学国家卓越工程师学院明月科创训练营集体合影',
    caption: '参加 2025 年暑季明月科创训练营，在“医工交叉”主题实践中与团队共同完成从需求理解到方案展示的项目过程。',
  },
  {
    src: '/mingyue/excellence-award.jpg',
    alt: '明月科创训练营卓越项目奖颁奖合影',
    caption: '团队项目获明月科创训练营卓越项目奖，在集中实践中完成协作、迭代与成果汇报。',
  },
  {
    src: '/mingyue/sutd-exchange.jpg',
    alt: '明月科创实验班新加坡科技设计大学交流活动合影',
    caption: '参与新加坡科技设计大学交流活动，接触设计、工程与创新创业融合的教育和实践视角。',
  },
  {
    src: '/mingyue/elite-institute.webp',
    alt: '重庆大学国家卓越工程师学院校园环境',
    caption: '在国家卓越工程师学院学习，把课程基础、工程训练与真实问题连接起来。',
  },
  {
    src: '/mingyue/class-workshop.webp',
    alt: '明月科创实验班创意实践活动合影',
    caption: '在创意实践中与同学协作，把开放想法逐步转化为可以展示和交流的成果。',
  },
  {
    src: '/mingyue/robot-training.webp',
    alt: '重庆大学机器人基础训练大赛师生合影',
    caption: '参与机器人基础训练与竞赛，在设计、调试和复盘中锻炼完整的工程实践能力。',
  },
  {
    src: '/mingyue/smart-expo.webp',
    alt: '明月科创实验班师生参观世界智能产业博览会',
    caption: '走进世界智能产业博览会，观察人工智能、机器人与智能制造如何进入真实产业场景。',
  },
  {
    src: '/mingyue/sports-meet.webp',
    alt: '重庆大学国家卓越工程师学院运动会集体合影',
    caption: '在运动会与集体活动中并肩投入，在课堂之外建立默契、归属感与团队精神。',
  },
  {
    src: '/mingyue/international-exchange.webp',
    alt: '明月科创实验班师生与国际交流嘉宾合影',
    caption: '通过交流活动接触不同背景下的工程教育与创新视角，在对话中拓宽认知边界。',
  },
];

// ROBOCON 经历照片：可在这里调整顺序、说明和替代文本。
export const roboconPhotos: CampusPhoto[] = [
  {
    src: '/robocon/team-2025.webp',
    alt: '重庆大学 GSing战队成员在第二十四届全国大学生机器人大赛现场合影',
    caption: '以 RCer 的身份走进赛场，与伙伴一起迎接真实工程问题和竞赛压力的检验。',
  },
  {
    src: '/robocon/robocon-spirit.webp',
    alt: '第二十四届全国大学生机器人大赛主题展示墙',
    caption: '热爱加持智慧，机动无界——赛场之外，是无数次方案讨论、调试与复盘。',
  },
  {
    src: '/robocon/competition-venue.webp',
    alt: '第二十四届全国大学生机器人大赛比赛场地入口',
    caption: '抵达比赛场地，让长时间的备赛积累走向正式验证。',
  },
  {
    src: '/robocon/team-2026.webp',
    alt: '重庆大学 GSing战队成员在第二十五届全国大学生机器人大赛现场合影',
    caption: '与战队成员并肩备赛，在新赛题中继续探索视觉感知与整机协同。',
  },
  {
    src: '/robocon/competition-flag.webp',
    alt: '第二十五届全国大学生机器人大赛校园旗帜',
    caption: '每一届赛题都是新的起点，也是一段从想法走向机器人实机的工程旅程。',
  },
  {
    src: '/robocon/robot-pit.webp',
    alt: '重庆大学 GSing战队成员在备赛区调试机器人',
    caption: '在备赛区贴近整机排查问题，让视觉算法、通信链路和机械动作真正配合起来。',
  },
  {
    src: '/robocon/field-test.webp',
    alt: 'ROBOCON 比赛现场正在进行机器人调试与场地验证',
    caption: '比赛现场的每一次测试，都在检验系统稳定性，也推动我们快速判断、协同和迭代。',
  },
];

// 校园艺术经历照片：图片文件放在 public/campus/，可在这里修改顺序、说明和替代文本。
export const campusPhotos: CampusPhoto[] = [
  {
    src: '/campus/opening-stage.webp',
    alt: '重庆大学学生艺术团管乐演出谢幕现场',
    caption: '在一次次登台与谢幕之间，感受合奏中彼此倾听的力量。',
  },
  {
    src: '/campus/clarinet-performance.webp',
    alt: '张航铭在重庆大学学生艺术团演奏单簧管',
    caption: '作为单簧管演奏员参与管乐队与交响乐队排练、演出。',
  },
  {
    src: '/campus/concert-group.webp',
    alt: '重庆大学学生艺术团专场音乐会演职人员合影',
    caption: '“同声 2025”专场音乐会，与伙伴共同完成舞台呈现。',
  },
  {
    src: '/campus/theatre-production.webp',
    alt: '重庆大学原创川剧演出团队合影',
    caption: '参与校园艺术活动，在多种舞台形式中理解协作与表达。',
  },
  {
    src: '/campus/spring-concert.webp',
    alt: '重庆大学学生艺术团新春演出合影',
    caption: '共同筹备演出，把长期排练沉淀为舞台上的默契。',
  },
  {
    src: '/campus/campus-theatre.webp',
    alt: '重庆大学校园艺术演出结束后观众与演职人员合影',
    caption: '艺术连接舞台与观众，也让校园生活拥有更丰富的温度。',
  },
  {
    src: '/campus/graduation-concert.webp',
    alt: '重庆大学2026年毕业音乐会现场',
    caption: '作为交响乐队副队长参与组织 2026 年毕业音乐会，协助排练统筹、成员沟通与现场演出执行。',
  },
];

export const honors: Honor[] = [
  {
    title: '第25届全国大学生机器人大赛 ROBOCON 仿生足式机器人挑战赛',
    level: '障碍赛 · 一等奖',
    description:
      '作为重庆大学仿生足式机器人挑战赛 1 队成员参加第25届全国大学生机器人大赛 ROBOCON，在障碍赛中获得一等奖。',
    year: '2026',
    category: '机器人竞赛',
    image: '/honors/robocon-2026-obstacle-first-v2.webp',
  },
  {
    title: '第25届全国大学生机器人大赛 ROBOCON 仿生足式机器人挑战赛',
    level: '任务赛 · 三等奖',
    description:
      '作为重庆大学仿生足式机器人挑战赛 1 队成员参加第25届全国大学生机器人大赛 ROBOCON，在任务赛中获得三等奖。',
    year: '2026',
    category: '机器人竞赛',
    image: '/honors/robocon-2026-mission-third-v2.webp',
  },
  {
    title: '美国大学生数学建模竞赛（MCM）',
    level: 'Honorable Mention · H 奖',
    description:
      '参加 2026 Mathematical Contest in Modeling，完成问题建模、计算分析、结果验证与英文论文协作，获 Honorable Mention。',
    year: '2026',
    category: '数学建模',
    image: '/honors/mcm-honorable-mention.webp',
  },
  {
    title: '重庆大学优秀学生综合奖学金',
    level: '乙等奖',
    description: '获评重庆大学 2024—2025 学年度第二学期优秀学生综合奖学金。',
    year: '2025.10',
    category: '奖学金',
    image: '/honors/scholarship-second.webp',
  },
  {
    title: 'ROBOCON 仿生足式机器人挑战赛',
    level: '障碍赛 · 国家二等奖',
    description: '第二十四届全国大学生机器人大赛 ROBOCON 仿生足式机器人挑战赛障碍赛。',
    year: '2025.08',
    category: '机器人竞赛',
    image: '/honors/robocon-obstacle-second.webp',
  },
  {
    title: 'ROBOCON 仿生足式机器人挑战赛',
    level: '越野赛 · 国家三等奖',
    description: '第二十四届全国大学生机器人大赛 ROBOCON 仿生足式机器人挑战赛越野赛。',
    year: '2025.08',
    category: '机器人竞赛',
    image: '/honors/robocon-offroad-third.webp',
  },
  {
    title: 'ROBOCON 仿生足式机器人挑战赛',
    level: '竞速赛 · 国家三等奖',
    description: '第二十四届全国大学生机器人大赛 ROBOCON 仿生足式机器人挑战赛竞速赛。',
    year: '2025.08',
    category: '机器人竞赛',
    image: '/honors/robocon-speed-third.webp',
  },
  {
    title: '中国国际大学生创新大赛（2025）',
    level: '重庆赛区选拔赛金奖',
    description: '项目在中国国际大学生创新大赛重庆赛区选拔赛中获金奖。',
    year: '2025.08',
    category: '科创竞赛',
    image: '/honors/innovation-gold.webp',
  },
  {
    title: 'SUTD DIVE 全球探索项目',
    level: '项目结业',
    description: '完成新加坡科技设计大学与重庆大学联合开展的 DIVE Global Exploration Opportunities 项目。',
    year: '2025.08',
    category: '国际研学',
    image: '/honors/sutd-dive.webp',
  },
  {
    title: '明月科创实验训练营',
    level: '卓越项目奖',
    description: '在 2025 年暑季明月科创训练营中展现出优秀的科创潜能与项目实践能力。',
    year: '2025.07',
    category: '科创实践',
    image: '/honors/mingyue-excellent-project.webp',
  },
  {
    title: '重庆大学学生科研训练计划（SRTP）',
    level: '项目结题 · 中等',
    description: '参与“硫化物还原六价铬研究中 AI 的应用及局限性”项目并完成结题。',
    year: '2025.07',
    category: '科研训练',
    image: '/honors/srtp-completion.webp',
  },
  {
    title: '重庆大学文艺先进个人',
    level: '校级荣誉',
    description: '获评重庆大学 2024—2025 学年度文艺先进个人。',
    year: '2025.07',
    category: '艺术实践',
    image: '/honors/arts-excellence.webp',
  },
  {
    title: '人工智能创新与创业研学项目',
    level: '项目结业',
    description: '完成日本人工智能创新与创业项目研学，在跨文化环境中探索 AI 与创新实践。',
    year: '2025.07',
    category: '国际研学',
    image: '/honors/japan-ai-program.webp',
  },
  {
    title: '重庆大学优秀共青团员',
    level: '校级荣誉',
    description: '获评 2024—2025 学年度优秀共青团员。',
    year: '2025.05',
    category: '综合荣誉',
    image: '/honors/outstanding-youth-league.webp',
  },
  {
    title: '重庆大学优秀学生综合奖学金',
    level: '丙等奖',
    description: '获评重庆大学 2024—2025 学年度第一学期优秀学生综合奖学金。',
    year: '2025.04',
    category: '奖学金',
    image: '/honors/scholarship-third.webp',
  },
  {
    title: '明月科创实验班 MINI CAMP',
    level: '最佳团队奖',
    description: '在 2025 年明月科创实验班 MINI CAMP 中展现出优秀的科创潜能与团队协作能力。',
    year: '2025.01',
    category: '科创实践',
    image: '/honors/minicamp-best-team.webp',
  },
  {
    title: '互联网英语听说挑战赛',
    level: '校级三等奖',
    description: '在 2024 年全国大学生创新发明大赛互联网英语听说挑战赛省初赛（校赛）中获三等奖。',
    year: '2024.11',
    category: '语言能力',
    image: '/honors/english-speaking-third.webp',
  },
  {
    title: '重庆大学机器人基础训练大赛 RMBC',
    level: '优秀奖',
    description: '在第二届重庆大学机器人基础训练大赛 RMBC 赛项中表现优异。',
    year: '2024.10',
    category: '机器人竞赛',
    image: '/honors/rmbc-excellence.webp',
  },
  {
    title: '重庆大学本科生军训',
    level: '优秀学员',
    description: '在 2024 级本科生军训工作中获评优秀学员。',
    year: '2024.09',
    category: '综合荣誉',
    image: '/honors/military-training.webp',
  },
];
