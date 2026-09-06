import type { CampusPhoto, Experience, Honor, Project } from '../types';

export const englishSiteData = {
  name: 'Hangming Zhang',
  identity: 'Robotics Engineering Undergraduate · Embedded Systems & AI Builder',
  intro: 'I work on robot perception, localization and navigation, embedded systems, computer vision, and intelligent hardware—turning ideas into reliable systems that solve real problems.',
  location: 'Chongqing University · Chongqing, China',
  about: {
    direction: 'I want to understand how robots perceive, decide, and act—and why they are needed in the first place. I break problems down from first principles, focus on user pain points through product thinking, and turn ideas into reliable, testable systems through engineering.',
    focus: 'Robotic perception, localization, navigation, and human–robot interaction in real environments, as well as turning complex technologies into clear, stable, and approachable product experiences.',
    purpose: 'Build robots and intelligent products that exist not merely to showcase technology, but to address real user pain points and create lasting value.',
    interests: 'Clarinet, orchestral performance, engineering design, product exploration, and documenting what I learn.',
  },
};

const projectText: Record<string, Partial<Project>> = {
  'smart-road-cone': {
    title: 'Smart Vehicle-Mounted Emergency Road Cone', type: 'Intelligent Hardware',
    summary: 'A remotely deployable roadside warning device designed to keep drivers away from dangerous traffic areas while making emergency deployment faster and safer.',
    role: 'System design, embedded control, interaction prototyping, and full-system integration', status: 'Prototype and user validation completed',
    background: 'Placing a conventional warning triangle after a roadside breakdown exposes the driver to moving traffic. This project explores a vehicle-mounted device that can deploy the warning marker remotely.',
    goal: 'Reduce the need for people to enter dangerous traffic areas and provide a clear, reliable emergency warning workflow.',
    solution: 'The prototype combines remote control, wireless communication, positioning and sensing, high-visibility lighting, voice prompts, status feedback, and a mobile interaction flow.',
    architecture: ['Mobile control', 'Wireless communication', 'ESP32-S3 controller', 'Positioning and sensing', 'Warning output'],
    workflow: ['User research', 'Requirement definition', 'Prototype design', 'System integration', 'User evaluation'],
    challenge: 'The system must balance portability, visibility, communication reliability, safety, and simple operation in stressful situations.',
    result: 'Completed a working prototype, on-site demonstration, and user evaluation, forming a closed loop from problem discovery to engineering validation.',
    galleryTitle: 'From Prototype to Field Demonstration', galleryDescription: 'The gallery documents the physical prototype, interaction design, exhibition setup, and on-site validation process.',
  },
  'robocon-vision': {
    title: 'ROBOCON Robot Vision & Perception System', type: 'Robot Vision',
    summary: 'A vision pipeline that recognizes supply-box categories and arithmetic expressions, then converts the calculation result into a color-based grasping decision for the robot.',
    role: 'Supply-box detection, arithmetic-expression recognition, decision logic, and robot communication', status: 'Continuously iterated',
    background: 'The competition robot must understand both the category of distributed supply boxes and an arithmetic expression before deciding which color target to grasp.',
    goal: 'Provide stable, real-time perception and an unambiguous target decision to the robot control system.',
    solution: 'YOLO detects and classifies supply boxes, a second recognition pipeline parses digits and operators, and a decision module evaluates the expression and maps its result to the required target category and box IDs.',
    architecture: ['Camera input', 'YOLO object detection', 'Expression recognition', 'Decision mapping', 'Robot communication'],
    workflow: ['Collect data', 'Train detectors', 'Parse expressions', 'Build decision logic', 'Integrate with robot'],
    challenge: 'The system must remain stable under changing viewpoints, clutter, occlusion, and competition-time constraints while keeping perception and control synchronized.',
    result: 'Completed supply-box and expression recognition, stable decision output, and integrated testing with the competition robot.',
    galleryTitle: 'Perception, Calculation, and Robot Decision', galleryDescription: 'Detection, expression parsing, and integrated decision screenshots show how vision results are transformed into actionable robot commands.',
  },
  'lidar-navigation': {
    title: 'LiDAR Mapping, Localization & Navigation', type: 'Localization & Navigation',
    summary: 'A ROS 2 navigation stack using Unitree L2 LiDAR, FAST-LIO2 mapping, FAST-LIO2 Localization with ICP, and Nav2 for planning and real-robot navigation.',
    role: 'Algorithm deployment, ROS 2 interface adaptation, Nav2 integration, and real-robot debugging', status: 'Validated on a real robot',
    background: 'Reliable indoor autonomy requires consistent mapping, localization, coordinate transforms, planning, and chassis control across multiple ROS 2 modules.',
    goal: 'Create a reusable pipeline from 3D LiDAR mapping and prior-map localization to autonomous navigation on a real robot.',
    solution: 'FAST-LIO2 fuses L2 LiDAR and IMU data for 3D mapping; FAST-LIO2 Localization and ICP align live scans to a prior map; the pose is then connected to Nav2 for global and local planning.',
    architecture: ['Unitree L2 LiDAR', 'FAST-LIO2 mapping', 'ICP localization', 'Nav2 planning', 'Chassis control'],
    workflow: ['Calibrate sensors', 'Build 3D map', 'Localize in prior map', 'Integrate Nav2', 'Validate on robot'],
    challenge: 'Key issues included sensor extrinsics, TF consistency, time synchronization, and stable conversion from 3D localization into the 2D navigation frame.',
    result: 'Completed 3D indoor mapping, prior-map localization, Nav2 path planning, and autonomous navigation verification on the physical robot.',
    galleryTitle: 'From 3D Mapping to Autonomous Navigation', galleryDescription: 'Mapping, localization, path planning, and real-robot tests document the full chain from point-cloud sensing to robot motion.',
  },
  'five-bar-robot': {
    title: 'Parallel Five-Bar Wheel-Leg Robot', type: 'Robot Control',
    summary: 'A wheel-leg robot integrating mechanical design, a mobile BLE controller, and an ESP32-S3 plus OV2640 camera-streaming web console.',
    role: 'Mechanical design, BLE controller, camera streaming console, and full-system integration', status: 'Full-system validation completed',
    background: 'The compact wheel-leg platform requires careful mechanical packaging, reliable remote control, and first-person visual feedback during operation.',
    goal: 'Design the mechanism and electronics layout while creating a safe, intuitive remote-control and camera-feedback workflow.',
    solution: 'The system combines a modeled five-bar mechanism, layered electronics packaging, BLE joystick control with emergency stop and mode switches, and a configurable OV2640 browser stream.',
    architecture: ['Five-bar mechanism', 'Low-level control', 'ESP32-S3 communication', 'BLE mobile controller', 'Camera web console'],
    workflow: ['Mechanical modeling', 'Electronics layout', 'BLE app development', 'Camera streaming', 'Robot validation'],
    challenge: 'The project required balancing kinematic clearance, structural strength, wiring space, control safety, Bluetooth robustness, and limited camera bandwidth.',
    result: 'Completed the mechanical assembly, BLE remote controller, real-time camera stream, browser controls, and integrated remote-operation tests.',
    galleryTitle: 'From Mechanical Design to Remote Operation', galleryDescription: 'Models, the physical robot, mobile controller, and camera console show the complete mechanical and embedded development process.',
  },
  'stirling-engine': {
    title: 'Stirling Engine Design & Fabrication', type: 'Mechanical Design',
    summary: 'A complete engineering exercise spanning 3D modeling, ADAMS mechanism simulation, fabrication, assembly, and heat-driven operation.',
    role: 'Mechanical modeling, ADAMS simulation, fabrication, assembly, and tuning', status: 'Physical prototype validated',
    background: 'A small Stirling engine is highly sensitive to sealing, friction, alignment, mechanism phase, and thermal stability.',
    goal: 'Design and fabricate a desktop Stirling engine that can sustain rotation under an external heat source.',
    solution: 'The engine was modeled in 3D, checked through ADAMS motion simulation, fabricated and assembled, then tuned through alignment, friction reduction, sealing, and heat-source adjustment.',
    architecture: ['Hot and cold ends', 'Displacer and power piston', 'Crank linkage', 'Flywheel', 'Frame and base'],
    workflow: ['Concept design', '3D assembly', 'ADAMS simulation', 'Fabrication', 'Thermal operation test'],
    challenge: 'Small deviations in sealing, concentricity, phase angle, or friction can prevent startup or interrupt continuous motion.',
    result: 'Completed the model and simulation, built the physical engine, and achieved continuous flywheel rotation under external heating.',
    galleryTitle: 'From Mechanism Model to Heat-Driven Motion', galleryDescription: 'The model, physical prototype, team photo, simulation, and operation video record the complete process.',
  },
  'jumping-robot': {
    title: 'Jumping Robot Development', type: 'Robot Design & Control',
    summary: 'Two prototype iterations exploring energy storage, release timing, and whole-body stability, culminating in a successful takeoff.',
    role: 'Mechanical concept, drive control, and system integration', status: 'Takeoff validated',
    background: 'Jumping requires rapid energy release and careful coordination among structure, actuation, mass distribution, and timing.',
    goal: 'Build a robot that can store and release energy autonomously to achieve a clear takeoff.',
    solution: 'After the first prototype moved but failed to lift off, the mechanism, transmission loss, effective stroke, mass distribution, and release timing were analyzed and iterated.',
    architecture: ['Energy storage', 'Drive unit', 'Control timing', 'Robot frame', 'Power and safety'],
    workflow: ['Build prototype one', 'Analyze failure', 'Iterate mechanism', 'Low-power tests', 'Validate final takeoff'],
    challenge: 'The first version exposed coupled issues in energy loss, mechanism travel, output timing, and center-of-mass stability.',
    result: 'The first prototype validated the motion chain; the final version achieved visible takeoff and completed a full failure-analysis and iteration cycle.',
    galleryTitle: 'From Failed Takeoff to Successful Jump', galleryDescription: 'Two real-world videos show the first failed attempt and the final successful takeoff after mechanical and control improvements.',
  },
  'math-modeling': {
    title: 'Mathematical Modeling Project', type: 'Modeling & Analysis',
    summary: 'A multi-stage model for sustainable Earth–Moon logistics, balancing cost, time, reliability, water resources, and environmental impact across elevator, rocket, and hybrid strategies.',
    role: 'Model design, computation, and technical writing', status: 'Completed',
    background: 'A long-term lunar base needs continuous infrastructure, cargo, and water transport, while elevators and rockets have different costs, risks, schedules, and environmental effects.',
    goal: 'Compare elevator-only, rocket-only, and hybrid logistics under system failures, resource constraints, and sustainability objectives.',
    solution: 'The study combines deterministic logistics, AHP evaluation, Monte Carlo risk simulation, BLSS and ISRU resource modeling, and NSGA-II multi-objective optimization.',
    architecture: ['Logistics scenarios', 'AHP evaluation', 'Monte Carlo risk', 'Water and ISRU', 'NSGA-II optimization'],
    workflow: ['Decompose problem', 'Build deterministic model', 'Add stochastic failures', 'Evaluate resources and environment', 'Sensitivity analysis and writing'],
    challenge: 'The work required integrating transport, risk, life-support, and environmental models within limited competition time while keeping the results interpretable.',
    result: 'Completed “Optimizing Earth-Moon Logistics: A Multi-Stage Approach for a Sustainable Lunar Colony” and received an Honorable Mention in the 2026 MCM.',
  },
};

const experienceText: Record<string, Partial<Experience>> = {
  bashu: { organization: 'Bashu Secondary School', role: 'High School', work: 'Completed my high-school education while taking part in class activities, sports events, and campus life. These three years helped me build a steady learning rhythm and remain focused under pressure.', growth: 'I developed habits of self-management, sustained effort, and responsibility, forming the foundation for later exploration in engineering, robotics, and music.' },
  mingyue: { period: '2024.09 — Present', organization: 'Chongqing University · Mingyue Innovation Program', role: 'National Elite Institute of Engineering · B.Eng. in Robotics Engineering', work: 'I study Robotics Engineering in the Mingyue Innovation Program at Chongqing University’s National Elite Institute of Engineering. The program uses interdisciplinary courses, inquiry-based learning, and project-driven education to develop design, engineering, and systems thinking.', growth: 'Through courses, innovation camps, robotics competitions, industry visits, and international exchange, I practice breaking down open-ended problems, building prototypes, validating ideas, and reflecting on results.' },
  gsing: { period: '2024 — Present', organization: 'GSing ROBOCON Team', role: 'RCer · Vision Team Member', work: 'I work on robot perception, target recognition, communication integration, and competition testing, collaborating with mechanical, electrical, and control teammates throughout long-term preparation.', growth: 'I learned how to move from code that works on a laptop to a system that performs reliably on the competition field—and how much ownership, communication, and teamwork matter.' },
  art: { period: '2024.09 — Present', organization: 'Chongqing University Student Art Troupe', role: 'Principal Clarinet · Deputy Orchestra Captain', work: 'I perform as a clarinetist and principal player in the wind ensemble and symphony orchestra. As deputy captain for 2025–2026, I also helped organize the 2026 graduation concert, coordinating rehearsals, members, and performance execution.', growth: 'Continuous performance sharpened my musical expression, while organizational work taught me to listen, take responsibility, and collaborate—skills that also shape my engineering practice.' },
};

const honorTitles: Record<string, string> = {
  '第25届全国大学生机器人大赛 ROBOCON 仿生足式机器人挑战赛': '25th China University Robot Competition ROBOCON — Biomimetic Legged Robot Challenge',
  '美国大学生数学建模竞赛（MCM）': 'Mathematical Contest in Modeling (MCM)',
  '重庆大学优秀学生综合奖学金': 'Chongqing University Outstanding Student Scholarship',
  'ROBOCON 仿生足式机器人挑战赛': 'ROBOCON Biomimetic Legged Robot Challenge',
  '中国国际大学生创新大赛（2025）': 'China International College Students’ Innovation Competition (2025)',
  'SUTD DIVE 全球探索项目': 'SUTD DIVE Global Exploration Program',
  '明月科创实验训练营': 'Mingyue Innovation Training Camp',
  '重庆大学学生科研训练计划（SRTP）': 'Chongqing University Student Research Training Program (SRTP)',
  '重庆大学文艺先进个人': 'Chongqing University Outstanding Individual in Arts',
  '人工智能创新与创业研学项目': 'AI Innovation and Entrepreneurship Program',
  '重庆大学优秀共青团员': 'Outstanding Communist Youth League Member, Chongqing University',
  '明月科创实验班 MINI CAMP': 'Mingyue Innovation Program MINI CAMP',
  '互联网英语听说挑战赛': 'Internet English Listening and Speaking Challenge',
  '重庆大学机器人基础训练大赛 RMBC': 'Chongqing University Robotics Basic Training Competition (RMBC)',
  '重庆大学本科生军训': 'Chongqing University Undergraduate Military Training',
};

const levelMap: Record<string, string> = { '一等奖': 'First Prize', '二等奖': 'Second Prize', '三等奖': 'Third Prize', '国家级 H 奖': 'Honorable Mention', '国家级': 'National Level', '校级': 'University Level', '院级': 'Institute Level', '优秀奖': 'Excellence Award', '结业证书': 'Certificate of Completion', '奖学金': 'Scholarship' };
const categoryMap: Record<string, string> = { '机器人竞赛': 'Robotics', '数学建模': 'Mathematical Modeling', '奖学金': 'Scholarship', '创新创业': 'Innovation', '国际交流': 'International Exchange', '科研训练': 'Research', '文艺实践': 'Arts', '综合荣誉': 'Comprehensive Honor', '课程实践': 'Course Project', '英语能力': 'English', '军训': 'Training' };

export function translateProjects(projects: Project[]) {
  return projects.map((project) => {
    const translated = projectText[project.id] ?? {};
    const photos = project.photos?.map((photo, index) => ({ ...photo, alt: `${translated.title ?? project.title} image ${index + 1}`, caption: `Project record ${index + 1}: ${translated.galleryDescription ?? translated.summary ?? project.summary}` }));
    const videos = project.videos?.map((video, index) => ({ ...video, title: `${translated.title ?? project.title} demonstration ${index + 1}`, caption: translated.galleryDescription ?? translated.result ?? video.caption }));
    return { ...project, ...translated, photos, videos };
  });
}

export function translateExperiences(experiences: Experience[]) {
  return experiences.map((experience) => ({ ...experience, ...(experience.id ? experienceText[experience.id] : undefined) }));
}

export function translateHonors(honors: Honor[]) {
  return honors.map((honor) => ({ ...honor, title: honorTitles[honor.title] ?? honor.title, level: levelMap[honor.level] ?? honor.level, category: categoryMap[honor.category] ?? honor.category, description: `Recognition for sustained work and achievement in ${categoryMap[honor.category] ?? honor.category.toLowerCase()}.` }));
}

export function translateGallery(photos: CampusPhoto[], subject: string) {
  return photos.map((photo, index) => ({ ...photo, alt: `${subject} photo ${index + 1}`, caption: `${subject} · moment ${index + 1}` }));
}
