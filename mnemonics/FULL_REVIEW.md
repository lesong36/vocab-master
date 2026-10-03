# 890词助记同类问题全量复核

审查日期：2026-10-03。范围：三、四、五年级上下册，890张词卡的主提示、视觉、语义、情境与构词，以及学习、闪卡、单元拼写和打印的共用展示。

读审发现并修订 **196张词卡**（三年级51、四年级49、五年级96）。其余694张保留现有具体声形或字形线索。逐词结论及引用的实际线索保存在三个 `audit-grade*.json` 的 `contentReview`，不是由格式校验自动判定的教学通过。

## 问题与处理

| 同类问题 | 实际例子 | 本轮处理 |
|---|---|---|
| 任意物件强配字母、嘴形强配拼写 | feel双e手指、rabbit双b耳朵、door双o圆钉 | 46张主提示精简成具体字母与声音；删去牵强联想、无用词源及重复解释 |
| 词义偏离当前例句 | free免费画空闲、old年龄画旧书、chicken鸡肉画鸡和蛋、drink动作画饮品 | 改为对应义项或删除不合适的图；clear主提示与晴朗天空例句对齐 |
| 通用流程没有定位目标 | pick、soil、begin、come out复用植物生长流程 | 删除相关图；共删除9条错位、泛化或陌生词源图解 |
| 依赖另一陌生词或历史片段 | ruler的rule、calligraphy的calli/graphy、astronaut的astro/naut、yesterday的yester | 隐藏4条拆词入口，保留可直接使用的字母线索 |
| 只重复分类、翻译 | blue只说颜色类别、animal只列动物名 | 删除27条重复语义内容及入口；允许没有适用语义线索 |
| 题目与要求的取回内容不匹配 | free问空闲还是免费、comfortable问舒适还是便利、后续词要求随意造句 | 重写为明确取回目标英文词或词组的中文提示 |

## 防止复发

- 所有词默认先显示“拼写线索”。“词义图”“用法与例句”按实际作用命名；不能把理解图当作拼写成果。没有具体图、可用构词或额外词义区别就不显示相应入口。
- 打印保留主线索、适用图解和一道回忆题，删除重复场景、语义段落和拆词说明。
- 单词与批量AI提示不再强制五维、350字或“整体记”兜底；优先一条实际字母线索，禁止虚构词根、双物件牵强配字母及口形猜拼写。
- 逐词审核绑定完整卡片内容。提示、例句或任一维度变化都会使旧审核失效；必须读审后更新证据，不得只重算哈希就宣称教学通过。
- 已知反例写入 `tests/test_mnemonic_quality.cjs`；`tests/test_mnemonic_quality_ui.py` 用实际组件检查890词默认主线索及空入口。

## 验收结果

- 890张词卡、36篇单元故事的资料、逐词审核与内容版本检查通过。
- 890词实际初始展示检查通过：默认显示本词拼写线索，不展示空构词或重复词义入口。
- 795个现有图解的实际页面渲染检查通过；890张打印卡片的A4尺寸检查通过。
- 学习、闪卡、单元拼写和回忆练习检查通过；收起时隐藏图、字母标记与例句，自查不写入学习记录。
- 已知反例、生成约束、空入口切换以及现有同步安全回归通过。375像素手机样例无横向溢出。

以上验收验证内容对应关系与产品行为，不把图解数量或测试通过当作儿童记忆效果证明。

## 编辑明细

| 年级 | 单元 | 单词 | 修订字段 |
|---|---|---|---|
| 3 | 三下Unit 1 | cap | 拼写主线索 |
| 3 | 三下Unit 1 | schoolbag | 回忆题或场景 |
| 3 | 三下Unit 1 | ruler | 构词 |
| 3 | 三下Unit 1 | English | 回忆题或场景 |
| 3 | 三下Unit 2 | cold | 拼写主线索 |
| 3 | 三下Unit 2 | raincoat | 回忆题或场景 |
| 3 | 三下Unit 3 | spring | 拼写主线索 |
| 3 | 三下Unit 3 | leaves | 回忆题或场景 |
| 3 | 三下Unit 3 | ice-skating | 回忆题或场景 |
| 3 | 三下Unit 3 | lot | 回忆题或场景 |
| 3 | 三下Unit 3 | sleep | 拼写主线索 |
| 3 | 三下Unit 5 | forty | 回忆题或场景 |
| 3 | 三下Unit 5 | half | 图示 |
| 3 | 三下Unit 5 | birthday | 回忆题或场景 |
| 3 | 三下Unit 6 | spacewoman | 回忆题或场景 |
| 3 | 三下Unit 6 | football | 回忆题或场景 |
| 3 | 三下Unit 7 | drink | 图示 |
| 3 | 三下Unit 7 | hot dog | 回忆题或场景 |
| 3 | 三下Unit 7 | chicken | 图示、回忆题或场景 |
| 3 | 三上Unit 1 | I | 回忆题或场景 |
| 3 | 三上Unit 1 | new | 图示 |
| 3 | 三上Unit 2 | old | 图示 |
| 3 | 三上Unit 2 | thirteen | 回忆题或场景 |
| 3 | 三上Unit 3 | sheep | 回忆题或场景 |
| 3 | 三上Unit 5 | child | 回忆题或场景 |
| 3 | 三上Unit 5 | floor | 图示 |
| 3 | 三上Unit 5 | blackboard | 回忆题或场景 |
| 3 | 三上Unit 6 | red scarf | 回忆题或场景 |
| 3 | 三上Unit 6 | rainbow | 回忆题或场景 |
| 3 | 三上Unit 7 | driver | 回忆题或场景 |
| 3 | 三上Unit 7 | singer | 回忆题或场景 |
| 3 | 三上Unit 7 | bed | 拼写主线索 |
| 3 | 三上Unit 7 | teacher | 回忆题或场景 |
| 4 | 四上Unit 1 | worried | 拼写主线索、回忆题或场景 |
| 4 | 四上Unit 1 | worry | 拼写主线索、回忆题或场景 |
| 4 | 四上Unit 1 | in time | 拼写主线索 |
| 4 | 四上Unit 1 | feel | 拼写主线索、回忆题或场景 |
| 4 | 四上Unit 1 | so | 拼写主线索、回忆题或场景 |
| 4 | 四上Unit 1 | model | 拼写主线索 |
| 4 | 四上Unit 1 | idea | 拼写主线索 |
| 4 | 四上Unit 2 | hard | 拼写主线索 |
| 4 | 四上Unit 2 | call | 拼写主线索 |
| 4 | 四上Unit 2 | little | 拼写主线索 |
| 4 | 四上Unit 2 | small | 拼写主线索 |
| 4 | 四上Unit 3 | excuse me | 拼写主线索 |
| 4 | 四上Unit 3 | door | 拼写主线索 |
| 4 | 四上Unit 5 | sandwich | 拼写主线索 |
| 4 | 四上Unit 5 | meatball | 回忆题或场景 |
| 4 | 四上Unit 5 | eat | 拼写主线索 |
| 4 | 四上Unit 5 | soup | 拼写主线索 |
| 4 | 四上Unit 5 | dessert | 回忆题或场景 |
| 4 | 四上Unit 5 | right | 拼写主线索 |
| 4 | 四上Unit 6 | without | 拼写主线索 |
| 4 | 四上Unit 6 | feed | 拼写主线索 |
| 4 | 四上Unit 6 | smell | 拼写主线索 |
| 4 | 四上Unit 6 | glass | 拼写主线索 |
| 4 | 四上Unit 6 | sun | 拼写主线索 |
| 4 | 四上Unit 7 | wish | 拼写主线索 |
| 4 | 四下Unit 1 | hobby | 拼写主线索 |
| 4 | 四下Unit 1 | kind | 回忆题或场景 |
| 4 | 四下Unit 1 | chess | 拼写主线索 |
| 4 | 四下Unit 1 | well | 拼写主线索 |
| 4 | 四下Unit 2 | fall | 拼写主线索 |
| 4 | 四下Unit 2 | crowd | 拼写主线索 |
| 4 | 四下Unit 2 | street | 拼写主线索 |
| 4 | 四下Unit 3 | fun | 拼写主线索 |
| 4 | 四下Unit 5 | chore | 拼写主线索 |
| 4 | 四下Unit 5 | the USA | 回忆题或场景 |
| 4 | 四下Unit 5 | flag | 拼写主线索 |
| 4 | 四下Unit 6 | rabbit | 拼写主线索 |
| 4 | 四下Unit 7 | need | 拼写主线索 |
| 4 | 四下Unit 7 | tell | 拼写主线索 |
| 4 | 四下Unit 7 | robot | 拼写主线索 |
| 4 | 四下Unit 7 | letter | 拼写主线索 |
| 4 | 四下Unit 7 | between | 拼写主线索 |
| 5 | 五上Unit 1 | difficult | 回忆题或场景 |
| 5 | 五上Unit 1 | Pigsy | 回忆题或场景 |
| 5 | 五上Unit 1 | calligraphy | 图示、回忆题或场景、构词 |
| 5 | 五上Unit 2 | fifteenth | 回忆题或场景 |
| 5 | 五上Unit 2 | eighth | 回忆题或场景 |
| 5 | 五上Unit 2 | usually | 回忆题或场景 |
| 5 | 五上Unit 2 | ninth | 回忆题或场景 |
| 5 | 五上Unit 2 | life (pl. lives) | 回忆题或场景 |
| 5 | 五上Unit 2 | care | 回忆题或场景 |
| 5 | 五上Unit 2 | Tomb-sweeping Day | 回忆题或场景 |
| 5 | 五上Unit 2 | national | 拼写主线索 |
| 5 | 五上Unit 3 | pick | 图示 |
| 5 | 五上Unit 3 | ourselves | 回忆题或场景 |
| 5 | 五上Unit 3 | myself | 回忆题或场景 |
| 5 | 五上Unit 3 | helper | 回忆题或场景 |
| 5 | 五上Unit 3 | poster | 拼写主线索 |
| 5 | 五上Unit 3 | recyclable | 回忆题或场景 |
| 5 | 五上Unit 5 | amazing | 回忆题或场景 |
| 5 | 五上Unit 5 | choice | 回忆题或场景 |
| 5 | 五上Unit 5 | high-speed train | 回忆题或场景 |
| 5 | 五上Unit 5 | convenient | 回忆题或场景 |
| 5 | 五上Unit 5 | clear | 拼写主线索、图示 |
| 5 | 五上Unit 6 | French | 回忆题或场景 |
| 5 | 五上Unit 6 | Canadian | 回忆题或场景 |
| 5 | 五上Unit 6 | bank | 回忆题或场景 |
| 5 | 五上Unit 6 | wonder | 回忆题或场景 |
| 5 | 五上Unit 6 | Washington | 回忆题或场景 |
| 5 | 五上Unit 7 | popular | 回忆题或场景 |
| 5 | 五上Unit 7 | British | 回忆题或场景 |
| 5 | 五上Unit 7 | exciting | 回忆题或场景 |
| 5 | 五下Unit 1 | yesterday | 构词 |
| 5 | 五下Unit 1 | free | 图示、回忆题或场景 |
| 5 | 五下Unit 1 | afraid | 回忆题或场景 |
| 5 | 五下Unit 2 | part | 回忆题或场景 |
| 5 | 五下Unit 2 | soil | 图示 |
| 5 | 五下Unit 2 | foot | 回忆题或场景 |
| 5 | 五下Unit 2 | growth | 回忆题或场景 |
| 5 | 五下Unit 2 | begin | 图示 |
| 5 | 五下Unit 2 | come out | 图示 |
| 5 | 五下Unit 3 | Teachers' Day | 回忆题或场景 |
| 5 | 五下Unit 3 | house | 回忆题或场景 |
| 5 | 五下Unit 5 | comfortable | 回忆题或场景 |
| 5 | 五下Unit 5 | off | 回忆题或场景 |
| 5 | 五下Unit 5 | sell | 回忆题或场景 |
| 5 | 五下Unit 5 | white | 词义说明、回忆题或场景 |
| 5 | 五下Unit 5 | online | 回忆题或场景 |
| 5 | 五下Unit 5 | goods | 回忆题或场景 |
| 5 | 五下Unit 6 | astronaut | 构词 |
| 5 | 五下Unit 6 | be interested in | 回忆题或场景 |
| 5 | 五下Unit 6 | writer | 回忆题或场景 |
| 5 | 五下Unit 6 | born | 回忆题或场景 |
| 5 | 五下Unit 6 | exercise | 回忆题或场景 |
| 5 | 五下Unit 6 | minute | 回忆题或场景 |
| 5 | 五下Unit 6 | take ... lesson | 回忆题或场景 |
| 5 | 五下Unit 6 | give up | 回忆题或场景 |
| 5 | 五下Unit 6 | scientist | 回忆题或场景 |
| 5 | 五下Unit 6 | the Medal of the Republic | 回忆题或场景 |
| 5 | 五下Unit 6 | honour | 回忆题或场景 |
| 5 | 五下Unit 6 | hybrid rice | 回忆题或场景 |
| 5 | 五下Unit 6 | once | 回忆题或场景 |
| 5 | 五下Unit 6 | farmer | 回忆题或场景 |
| 5 | 五下Unit 6 | invent | 回忆题或场景 |
| 5 | 五下Unit 6 | output | 回忆题或场景 |
| 5 | 五下Unit 6 | each | 回忆题或场景 |
| 5 | 五下Unit 7 | square | 回忆题或场景 |
| 5 | 五下Unit 7 | the Summer Palace | 回忆题或场景 |
| 5 | 五下Unit 7 | well-kept | 回忆题或场景 |
| 5 | 五下Unit 7 | colourful | 回忆题或场景 |
| 5 | 五下Unit 7 | international | 回忆题或场景 |
| 5 | 五下Unit 7 | airport | 回忆题或场景 |
| 5 | 五下Unit 7 | modern | 回忆题或场景 |
| 5 | 五下Unit 7 | computer | 回忆题或场景 |
| 5 | 五下Unit 7 | subway | 回忆题或场景 |
| 5 | 五下Unit 7 | line | 回忆题或场景 |
| 5 | 五下Unit 7 | its | 回忆题或场景 |
| 5 | 五下Unit 7 | Beijing roast duck | 回忆题或场景 |
| 5 | 五下Unit 7 | hot pot | 回忆题或场景 |
| 5 | 五下Unit 7 | Central Axis | 回忆题或场景 |
| 5 | 五下Unit 7 | Bell and Drum Towers | 回忆题或场景 |
| 5 | 五下Unit 7 | northern | 回忆题或场景 |
| 5 | 五下Unit 7 | end | 回忆题或场景 |
| 5 | 五下Unit 7 | bird's-eye view | 回忆题或场景 |
| 5 | 五下Unit 7 | the Palace Museum | 回忆题或场景 |
| 5 | 五下Unit 7 | wooden | 回忆题或场景 |
| 5 | 五下Unit 7 | palace | 回忆题或场景 |
| 5 | 五下Unit 7 | treasure | 回忆题或场景 |
| 5 | 五下Unit 7 | bus | 回忆题或场景 |
| 5 | 五下Unit 7 | gate | 回忆题或场景 |
| 5 | 五下Unit 7 | Tian'anmen Square Complex | 回忆题或场景 |
| 5 | 五下Unit 7 | southern | 回忆题或场景 |
| 5 | 五下Unit 7 | own | 回忆题或场景 |
| 5 | 五下Unit 7 | young | 回忆题或场景 |
| 5 | 五下Unit 7 | Bird's Nest | 回忆题或场景 |
| 5 | 五下Unit 7 | well-known | 回忆题或场景 |
| 5 | 五下Unit 7 | hold | 回忆题或场景 |
| 5 | 五下Unit 7 | ceremony | 回忆题或场景 |
| 3 | 三下Unit 3 | fish | 词义说明 |
| 3 | 三下Unit 5 | art | 词义说明 |
| 3 | 三上Unit 2 | panda | 词义说明 |
| 3 | 三上Unit 3 | cow | 词义说明 |
| 3 | 三上Unit 3 | horse | 词义说明 |
| 3 | 三上Unit 3 | elephant | 词义说明 |
| 3 | 三上Unit 3 | cat | 词义说明 |
| 3 | 三上Unit 5 | piano | 词义说明 |
| 3 | 三上Unit 6 | black | 词义说明 |
| 3 | 三上Unit 6 | yellow | 词义说明 |
| 3 | 三上Unit 6 | blue | 词义说明 |
| 3 | 三上Unit 6 | green | 词义说明 |
| 3 | 三上Unit 6 | red | 词义说明 |
| 3 | 三上Unit 6 | brown | 词义说明 |
| 3 | 三上Unit 6 | purple | 词义说明 |
| 3 | 三上Unit 6 | grape | 词义说明 |
| 3 | 三上Unit 6 | flower | 词义说明 |
| 3 | 三上Unit 6 | butterfly | 词义说明 |
| 4 | 四上Unit 1 | dog | 词义说明 |
| 4 | 四上Unit 1 | plane | 词义说明 |
| 4 | 四上Unit 2 | animal | 词义说明 |
| 4 | 四上Unit 3 | monkey | 词义说明 |
| 4 | 四上Unit 3 | banana | 词义说明 |
| 4 | 四上Unit 5 | apple | 词义说明 |
| 4 | 四上Unit 6 | pig | 词义说明 |

## 依据与验收界限

词义核对使用教材例句和[Cambridge的poster词条](https://dictionary.cambridge.org/dictionary/english/poster)、[clear词条](https://dictionary.cambridge.org/dictionary/english/clear)等。拼写分块作为编排依据，不声称是词根或音节数量。

结构、版本、页面行为与排版回归不测量儿童学习效果。是否能稍后独立回忆，需要实际练习观察；保留的线索也可依据孩子使用结果继续替换。
