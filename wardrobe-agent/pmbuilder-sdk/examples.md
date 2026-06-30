
### 调用PMBuilder SDK，生成的参数化脚本示例:
```javascript
/*---- 定义顶层模型(组合柜)变量（参数） -----*/
// -----------创建float变量--------------
// #WY: 组合柜最左边距离原点的位移 (X方向)
const paramWY = PMBuilder.createParam('#WY', '0', 'float', '组合柜X起点', 1, { min: '0', max: '10000' });
// #W: 组合柜总宽度 = 300 + 900 + 300 = 1500mm
const paramW = PMBuilder.createParam('#W', '1500', 'float', '组合柜总宽', 1, { min: '300', max: '10000' });
// #D: 总深度 = 2400mm
const paramD = PMBuilder.createParam('#D', '2400', 'float', '组合柜总深', 1, { min: '300', max: '4000' });
// #H: 总高度 = 500mm
const paramH = PMBuilder.createParam('#H', '500', 'float', '组合柜总高', 1, { min: '100', max: '2800' });
// #W_LEFT: 左圆弧封板柜宽度 = 300mm
const paramWLeft = PMBuilder.createParam('#W_LEFT', '300', 'float', '左柜宽度', 1, { min: '100', max: '600' });
// #W_MID: 拱形高柜宽度 = 900mm
const paramWMid = PMBuilder.createParam('#W_MID', '900', 'float', '中柜宽度', 1, { min: '200', max: '1200' });
PMBuilder.createParam('#Z_QSKCZ', '1', 'float', '收口材质选择', 2, { min: '', max: '', group: '▶收口设置-组◀', ignore: '', editorOptions: [{ name: '柜体色', value: '0' }, { name: '门板色', value: '1' }] });
// 创建复合公式变量-当前值为公式
PMBuilder.createParam('#COMP_SPEL', '', 'float', '复合公式-公式', 4, { min: '0', max: '99', group: '自定义变量', ignore: '', status: 1, formula: '#W+#D' });
// 创建复合公式变量-当前值为值
PMBuilder.createParam('#COMP_VALUE', '60', 'float', '复合公式-值', 4, { min: '0', max: '99', group: '自定义变量', ignore: '', status: 0, formula: '#W+#D' });
// 创建复合公式+可选值变量 - 当前值为值
PMBuilder.createParam('#GSKX', '20', 'float', '公式可选-值', 7, { min: '', max: '', group: '自定义变量', ignore: '', editorOptions: [{ name: '20', value: '20' }, { name: '30', value: '30' }], formula: '#W+#D' });
// 创建固定值变量（paramTypeId=0）
PMBuilder.createParam('#FIXED_VAL', '100', 'float', '固定值变量', 0);
// 创建单值变量（paramTypeId=1）
PMBuilder.createParam('#SINGLE_VAL', '200', 'float', '单值变量', 1, { min: '0', max: '1000' });
// 创建枚举变量（paramTypeId=2）
PMBuilder.createParam('#ENUM_VAL', '1', 'float', '枚举变量', 2, { min: '', max: '', editorOptions: [{ name: '选项A', value: '0' }, { name: '选项B', value: '1' }] });
// 创建复合公式变量（paramTypeId=4, status=0）
PMBuilder.createParam('#COMP_FORMULA_S0', '60', 'float', '复合公式-状态0', 4, { min: '0', max: '99', group: '自定义变量', ignore: '', status: 0, formula: '#W+#D' });
// 创建固定公式变量（paramTypeId=5）
PMBuilder.createParam('#FIX_FORMULA', '', 'float', '固定公式变量', 5, { formula: '#W*2' });
// 创建公式可选变量（paramTypeId=7）
PMBuilder.createParam('#FORMULA_OPT', '20', 'float', '公式可选变量', 7, { min: '', max: '', group: '自定义变量', ignore: '', editorOptions: [{ name: '20', value: '20' }, { name: '30', value: '30' }], formula: '#W+#D' });

// -----------创建material变量----------------
PMBuilder.createParam("CZBL", '3FO3WBH547SJ', 'material', "我的材质", 0);
PMBuilder.createParam("CZBL2", '3FO40H8E6V0K', 'material', "可选材质变量", 2, {link: "3FO4K5T6AX6D", linkForm: 0});
PMBuilder.createParam("CZBL3", '3FO40H8GPWB7', 'material', "可选带条件材质变量", 2, {link: "{\"cases\":[{\"condition\":\"#W==50\",\"value\":\"3FO4K5T6LQ0L\"}],\"defaultValue\":\"3FO4K5T6LQ0L\"}", linkForm: 1});
PMBuilder.createParam("CZBL4", '3FO40H8GPWB7', 'material', "复合公式材质变量", 4, {link: "3FO4K5T6LQ0L", linkForm: 0, formula: "#CZBL3", status: 0, formulaForm: 0});
PMBuilder.createParam("CZBL5", '', 'material', "固定公式材质变量", 5, {formula: "#CZ"});
PMBuilder.createParam("CZBL6", '3FO40H8GPWB7', 'material', "复合公式公式类型材质变量", 4, {formula:"{\"cases\":[{\"condition\":\"#D==50\",\"value\":\"3FO45EF07A54\"}],\"defaultValue\":\"3FO416J23I6B\"}",formulaForm: 1, status: 0, link: 
"{\"cases\":[{\"condition\":\"#W==50\",\"value\":\"3FO4K6PPM39U\"}],\"defaultValue\":\"3FO4K5T6LQ0L\"}", linkForm:1});
// 创建复合公式材质变量（paramTypeId=4, status=1）
PMBuilder.createParam("CZBL7", '3FO40H8GPWB7', 'material', "复合公式材质变量-状态1", 4, {link: "3FO4K5T6LQ0L", linkForm: 0, formula: "#CZBL3", status: 1, formulaForm: 0});

// -----------创建style变量-----------------
PMBuilder.createParam("YSBL", '{"obsBrandGoodId":"3FO3LEDJYG4C","versionId":0}', 'style', "我的样式", 0);
// 创建enum类型的样式变量，linkForm为0表示link是一个指定样式包的id
PMBuilder.createParam("YSBL_ENUM", '{"obsBrandGoodId":"3FO3JPJBAOR0","versionId":2}', 'style', "样式枚举", 2, {link: "3FO4K7CQ6O0P", linkForm: "0"});
// 创建enum类型的样式变量，linkForm为1表示link是一个带条件的样式包id列表，哪个条件为真，实际生效的就是哪个id
PMBuilder.createParam("YSBL_ENUM2", '{"obsBrandGoodId":"3FO3QBR7GSYY","versionId":4}', 'style', "样式枚举2", 2, {link: '{"cases":[{"condition":"#W == 600","value":"3FO4K5PX1APN"}],"defaultValue":"3FO4K7CQ6O0P"}', linkForm: "1"});
// 创建复合公式的样式变量，公式是条件，当前值为某个条件的取值
PMBuilder.createParam('#Z_ZSKKS', '{"obsBrandGoodId":"3FO3NGTYT0MM","versionId":5}', 'style', '左收口款式', 4, { min: '', max: '', group: '▶左收口设置-组◀', ignore: '', formulaForm: 1, link: "3FO4K7M0BUAQ", linkForm: 0,status: 1, formula: { cases: [{ condition: '#W==200', value: '{"obsBrandGoodId":"3FO3NGURA302","versionId":10}' }, { condition: '#W==300', value: '{"obsBrandGoodId":"3FO3K04GWD9L","versionId":6}' }], defaultValue: '{"obsBrandGoodId":"3FO3NGTYT0MM","versionId":5}' } });
// 创建复合公式样式变量（paramTypeId=4, status=0, linkForm=0, formulaForm=0）
PMBuilder.createParam("YSBL_FORMULA_S0_L0_F0", '{"obsBrandGoodId":"3FO3LEDJYG4C","versionId":0}', 'style', "复合公式样式-状态0-link0-公式0", 4, {link: "3FO4K7CQ6O0P", linkForm: "0", formula: "#YSBL", status: 0, formulaForm: 0});
// 创建复合公式样式变量（paramTypeId=4, status=0, linkForm=1, formulaForm=0）
PMBuilder.createParam("YSBL_FORMULA_S0_L1_F0", '{"obsBrandGoodId":"3FO3LEDJYG4C","versionId":0}', 'style', "复合公式样式-状态0-link1-公式0", 4, {link: '{"cases":[{"condition":"#W == 600","value":"3FO4K5PX1APN"}],"defaultValue":"3FO4K7CQ6O0P"}', linkForm: "1", formula: "#YSBL", status: 0, formulaForm: 0});
// 创建复合公式样式变量（paramTypeId=4, status=0, linkForm=0, formulaForm=1）
PMBuilder.createParam("YSBL_FORMULA_S0_L0_F1", '{"obsBrandGoodId":"3FO3NGTYT0MM","versionId":5}', 'style', "复合公式样式-状态0-link0-公式1", 4, {link: "3FO4K7M0BUAQ", linkForm: "0", formula: { cases: [{ condition: '#W==200', value: '{"obsBrandGoodId":"3FO3NGURA302","versionId":10}' }, { condition: '#W==300', value: '{"obsBrandGoodId":"3FO3K04GWD9L","versionId":6}' }], defaultValue: '{"obsBrandGoodId":"3FO3NGTYT0MM","versionId":5}' }, status: 0, formulaForm: 1});
// 创建复合公式样式变量（paramTypeId=4, status=0, linkForm=1, formulaForm=1）
PMBuilder.createParam("YSBL_FORMULA_S0_L1_F1", '{"obsBrandGoodId":"3FO3NGTYT0MM","versionId":5}', 'style', "复合公式样式-状态0-link1-公式1", 4, {link: '{"cases":[{"condition":"#W == 600","value":"3FO4K5PX1APN"}],"defaultValue":"3FO4K7CQ6O0P"}', linkForm: "1", formula: { cases: [{ condition: '#W==200', value: '{"obsBrandGoodId":"3FO3NGURA302","versionId":10}' }, { condition: '#W==300', value: '{"obsBrandGoodId":"3FO3K04GWD9L","versionId":6}' }], defaultValue: '{"obsBrandGoodId":"3FO3NGTYT0MM","versionId":5}' }, status: 0, formulaForm: 1});
// 创建复合公式样式变量（paramTypeId=4, status=1, linkForm=0, formulaForm=0）
PMBuilder.createParam("YSBL_FORMULA_S1_L0_F0", '{"obsBrandGoodId":"3FO3LEDJYG4C","versionId":0}', 'style', "复合公式样式-状态1-link0-公式0", 4, {link: "3FO4K7CQ6O0P", linkForm: "0", formula: "#YSBL", status: 1, formulaForm: 0});
// 创建复合公式样式变量（paramTypeId=4, status=1, linkForm=1, formulaForm=0）
PMBuilder.createParam("YSBL_FORMULA_S1_L1_F0", '{"obsBrandGoodId":"3FO3LEDJYG4C","versionId":0}', 'style', "复合公式样式-状态1-link1-公式0", 4, {link: '{"cases":[{"condition":"#W == 600","value":"3FO4K5PX1APN"}],"defaultValue":"3FO4K7CQ6O0P"}', linkForm: "1", formula: "#YSBL", status: 1, formulaForm: 0});
// 创建复合公式样式变量（paramTypeId=4, status=1, linkForm=1, formulaForm=1）
PMBuilder.createParam("YSBL_FORMULA_S1_L1_F1", '{"obsBrandGoodId":"3FO3NGTYT0MM","versionId":5}', 'style', "复合公式样式-状态1-link1-公式1", 4, {link: '{"cases":[{"condition":"#W == 600","value":"3FO4K5PX1APN"}],"defaultValue":"3FO4K7CQ6O0P"}', linkForm: "1", formula: { cases: [{ condition: '#W==200', value: '{"obsBrandGoodId":"3FO3NGURA302","versionId":10}' }, { condition: '#W==300', value: '{"obsBrandGoodId":"3FO3K04GWD9L","versionId":6}' }], defaultValue: '{"obsBrandGoodId":"3FO3NGTYT0MM","versionId":5}' }, status: 1, formulaForm: 1});
// 创建固定公式样式变量（paramTypeId=5）
PMBuilder.createParam("YSBL_FIXED_FORMULA", '', 'style', "固定公式样式变量", 5, {formula: "#YSBL"});

// ------------创建shape变量------------------
PMBuilder.createParam('#PROFILE', '3FO3JWQIRM4X', 'shape', '截面轮廓', 0);
PMBuilder.createParam('#PROFILE_FIX', '3FO3JWQIRM4X', 'shape', '固定截面', 6);
// 创建enum类型的轮廓变量, linkForm为0表示link是一个指定文件夹的id
PMBuilder.createParam('#PROFILE_ENUM', '3FO40HN8PCFQ', 'shape', '轮廓样式', 2, {link: "3FO4K5T6QLJ2", linkForm: "0"});
// 创建enum类型的轮廓变量, linkForm为1表示link是一个带条件的文件夹id列表，哪个条件为真，实际生效的就是哪个id
PMBuilder.createParam('#PROFILE_ENUM2', '3FO40HN6UAEA', 'shape', '轮廓样式', 2, {link: '{"cases":[{"condition":"#W==50","value":"3FO4K5T6QLJ2"}],"defaultValue":"3FO4K5T67V6G"}', linkForm: "1"});
// 创建复合公式轮廓变量（paramTypeId=4, status=0, linkForm=0, formulaForm=0）
PMBuilder.createParam('#PROFILE_FORMULA_S0_L0_F0', '3FO3JWQIRM4X', 'shape', '复合公式轮廓-状态0-link0-公式0', 4, {link: "3FO4K5T6QLJ2", linkForm: "0", formula: "#PROFILE", status: 0, formulaForm: 0});
// 创建复合公式轮廓变量（paramTypeId=4, status=0, linkForm=1, formulaForm=0）
PMBuilder.createParam('#PROFILE_FORMULA_S0_L1_F0', '3FO3JWQIRM4X', 'shape', '复合公式轮廓-状态0-link1-公式0', 4, {link: '{"cases":[{"condition":"#W==50","value":"3FO4K5T6QLJ2"}],"defaultValue":"3FO4K5T67V6G"}', linkForm: "1", formula: "#PROFILE", status: 0, formulaForm: 0});
// 创建复合公式轮廓变量（paramTypeId=4, status=0, linkForm=0, formulaForm=1）
PMBuilder.createParam('#PROFILE_FORMULA_S0_L0_F1', '3FO40HN8PCFQ', 'shape', '复合公式轮廓-状态0-link0-公式1', 4, {link: "3FO4K5T6QLJ2", linkForm: "0", formula: { cases: [{ condition: '#W==50', value: '3FO40HN8PCFQ' }, { condition: '#W==100', value: '3FO40HN6UAEA' }], defaultValue: '3FO3JWQIRM4X' }, status: 0, formulaForm: 1});
// 创建复合公式轮廓变量（paramTypeId=4, status=0, linkForm=1, formulaForm=1）
PMBuilder.createParam('#PROFILE_FORMULA_S0_L1_F1', '3FO40HN8PCFQ', 'shape', '复合公式轮廓-状态0-link1-公式1', 4, {link: '{"cases":[{"condition":"#W==50","value":"3FO4K5T6QLJ2"}],"defaultValue":"3FO4K5T67V6G"}', linkForm: "1", formula: { cases: [{ condition: '#W==50', value: '3FO40HN8PCFQ' }, { condition: '#W==100', value: '3FO40HN6UAEA' }], defaultValue: '3FO3JWQIRM4X' }, status: 0, formulaForm: 1});
// 创建复合公式轮廓变量（paramTypeId=4, status=1, linkForm=0, formulaForm=0）
PMBuilder.createParam('#PROFILE_FORMULA_S1_L0_F0', '3FO3JWQIRM4X', 'shape', '复合公式轮廓-状态1-link0-公式0', 4, {link: "3FO4K5T6QLJ2", linkForm: "0", formula: "#PROFILE", status: 1, formulaForm: 0});
// 创建复合公式轮廓变量（paramTypeId=4, status=1, linkForm=1, formulaForm=0）
PMBuilder.createParam('#PROFILE_FORMULA_S1_L1_F0', '3FO3JWQIRM4X', 'shape', '复合公式轮廓-状态1-link1-公式0', 4, {link: '{"cases":[{"condition":"#W==50","value":"3FO4K5T6QLJ2"}],"defaultValue":"3FO4K5T67V6G"}', linkForm: "1", formula: "#PROFILE", status: 1, formulaForm: 0});
// 创建复合公式轮廓变量（paramTypeId=4, status=1, linkForm=0, formulaForm=1）
PMBuilder.createParam('#PROFILE_FORMULA_S1_L0_F1', '3FO40HN8PCFQ', 'shape', '复合公式轮廓-状态1-link0-公式1', 4, {link: "3FO4K5T6QLJ2", linkForm: "0", formula: { cases: [{ condition: '#W==50', value: '3FO40HN8PCFQ' }, { condition: '#W==100', value: '3FO40HN6UAEA' }], defaultValue: '3FO3JWQIRM4X' }, status: 1, formulaForm: 1});
// 创建复合公式轮廓变量（paramTypeId=4, status=1, linkForm=1, formulaForm=1）
PMBuilder.createParam('#PROFILE_FORMULA_S1_L1_F1', '3FO40HN8PCFQ', 'shape', '复合公式轮廓-状态1-link1-公式1', 4, {link: '{"cases":[{"condition":"#W==50","value":"3FO4K5T6QLJ2"}],"defaultValue":"3FO4K5T67V6G"}', linkForm: "1", formula: { cases: [{ condition: '#W==50', value: '3FO40HN8PCFQ' }, { condition: '#W==100', value: '3FO40HN6UAEA' }], defaultValue: '3FO3JWQIRM4X' }, status: 1, formulaForm: 1});
// 创建固定公式轮廓变量（paramTypeId=5）
PMBuilder.createParam('#PROFILE_FIXED_FORMULA', '', 'shape', '固定公式轮廓变量', 5, {formula: "#PROFILE"});

// ------------创建booleanlist变量------------------
// 创建多布尔变量：value为选项权重和(选项的权重值是1，2，4，8...2^n)；paramTypeId仅0（single）或6（constant），options.valueDisplayNames 必填，为各布尔项显示名
// 选中了“左”和“前”，则value为1+4=5
PMBuilder.createParam('#SK_XZ', '5', 'booleanlist', '四边显示', 0, { valueDisplayNames: ['左', '右', '前', '后'] });
// 如果全选，value为1+2+4+8=15
PMBuilder.createParam('#SK_XZ2', '15', 'booleanlist', '四边显示', 0, { valueDisplayNames: ['左', '右', '前', '后'] });
// 如果全不选，value为0
PMBuilder.createParam('#SK_XZ3', '0', 'booleanlist', '四边显示', 0, { valueDisplayNames: ['左', '右', '前', '后'] });

/*---- 定义单元柜实例 -----*/
// 定位点是左后下点
// X方向: 从 #WY 开始，依次排列
// Y方向: 定位点在后, Y=0
// Z方向: 定位点在下, Z=0

// 1. 左圆弧封板柜: X起点 = #WY
const leftCabinet = PMBuilder.createModelInstance('3FO4BHGXK7WU');
PMBuilder.setPosition(leftCabinet, '#WY', '0', '0');
PMBuilder.setRotation(leftCabinet, '0', '0', '0');
PMBuilder.setParam(leftCabinet, '#W', '#W_LEFT');

// 2. 拱形高柜: X起点 = #WY + 300
const midCabinet = PMBuilder.createModelInstance('3FO4BV8RP55Q');
PMBuilder.setPosition(midCabinet, '(#WY+300)', '0', '0');
PMBuilder.setRotation(midCabinet, '0', '0', '0');
PMBuilder.setParam(midCabinet, '#W', '#W_MID');

// 3. 右圆弧封板柜: X起点 = #WY + 300 + 900 = #WY + 1200
const rightCabinet = PMBuilder.createModelInstance('3FO4BHGXJJIN');
PMBuilder.setPosition(rightCabinet, '(#WY+1200)', '0', '0');
PMBuilder.setRotation(rightCabinet, '0', '0', '0');
PMBuilder.setParam(rightCabinet, '#W', '(#W-#W_LEFT-#W_MID)');
// 设置材质变量
PMBuilder.setParam(rightCabinet, '#materialBrandGoodId', '3FO3WBH547SJ');
// 设置样式变量
PMBuilder.setParam(rightCabinet, '#Z_NB1TH', '{"versionId":15,"obsBrandGoodId":"3FO3Q5PP7MDK"}');
// 设置隐藏条件
PMBuilder.setParam(rightCabinet, '#ignore', '#W==3000');
// 设置调用点为左后下
PMBuilder.setParam(rightCabinet, '#invokedPosType', '2');
// 设置实例样式（functionName）
PMBuilder.setParam(rightCabinet, '#functionName', '#YSBL');
```