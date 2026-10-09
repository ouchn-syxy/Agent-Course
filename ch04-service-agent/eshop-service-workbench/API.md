# 网店客服模拟平台 — API 接口文档

Base URL: `http://localhost:8000`

---

## 1. 客户相关

### 1.1 获取客户列表

> GET `/api/customers`

返回所有客户及其最新消息摘要，用于左侧消息列表渲染。

**响应示例：**

```json
[
  {
    "id": "cust_001",
    "name": "张三",
    "avatar": "👩",
    "level": "VIP会员",
    "last_message": "你好，我看中了你家那条红色连衣裙...",
    "last_message_time": "2026-07-15 21:37:38",
    "last_sender": "customer",
    "unread_count": 0,
    "is_handled": false,
    "need_human": false
  }
]
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 客户唯一标识 |
| `name` | string | 客户姓名 |
| `avatar` | string | 头像 emoji |
| `level` | string | 会员等级（VIP会员 / 普通会员 / 新用户） |
| `last_message` | string | 最新一条消息内容（截取前 50 字） |
| `last_message_time` | string | 最新消息时间，格式 `YYYY-MM-DD HH:MM:SS` |
| `last_sender` | string | 最新消息发送方：`customer` / `agent` |
| `unread_count` | number | 未读客户消息数（已有客服回复则为 0） |
| `is_handled` | boolean | 对话是否已处理完毕（客户说了 `[END]`） |
| `need_human` | boolean | 是否需要转人工（预留） |

---

### 1.2 获取客户详情

> GET `/api/customers/{customer_id}`

返回客户个人信息和历史订单。

**响应示例：**

```json
{
  "id": "cust_001",
  "name": "张三",
  "avatar": "👩",
  "level": "VIP会员",
  "orders": [
    {
      "order_id": "20230701-0001",
      "date": "2026-07-01",
      "status": "已签收",
      "items": [
        {
          "product_id": "P001",
          "product_name": "红色连衣裙",
          "price": 299.00,
          "quantity": 1,
          "size": "M",
          "color": "红色"
        }
      ],
      "total": 299.00
    }
  ],
  "persona": "售前咨询型客户，正在浏览商品..."
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 客户 ID |
| `name` | string | 姓名 |
| `avatar` | string | 头像 emoji |
| `level` | string | 会员等级 |
| `orders` | array | 历史订单列表 |
| `orders[].order_id` | string | 订单号 |
| `orders[].date` | string | 下单日期 |
| `orders[].status` | string | 订单状态（已签收 / 待发货 / 运输中 等） |
| `orders[].items` | array | 订单商品明细 |
| `orders[].items[].product_id` | string | 商品 ID |
| `orders[].items[].product_name` | string | 商品名称 |
| `orders[].items[].price` | number | 单价 |
| `orders[].items[].quantity` | number | 数量 |
| `orders[].items[].size` | string | 尺码 |
| `orders[].items[].color` | string | 颜色 |
| `orders[].total` | number | 订单总金额 |
| `persona` | string | 客户人设描述（LLM 模拟用） |

**错误：**

| 状态码 | 说明 |
|--------|------|
| 404 | 客户不存在 |

---

## 2. 聊天相关

### 2.1 获取聊天记录

> GET `/api/chat/{customer_id}`

获取与指定客户的完整聊天记录。

**响应示例：**

```json
{
  "customer_id": "cust_001",
  "customer_name": "张三",
  "messages": [
    {
      "id": "a1b2c3d4...",
      "sender": "customer",
      "content": "你好，我看中了你家那条红色连衣裙...",
      "timestamp": "2026-07-15 21:37:38"
    },
    {
      "id": "e5f6g7h8...",
      "sender": "agent",
      "content": "亲，M码红色有货的哦～您身高160体重55，M码刚好合适！",
      "timestamp": "2026-07-15 21:38:10"
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `customer_id` | string | 客户 ID |
| `customer_name` | string | 客户姓名 |
| `messages` | array | 消息列表（时间正序） |
| `messages[].id` | string | 消息唯一 ID |
| `messages[].sender` | string | 发送方：`customer` / `agent` |
| `messages[].content` | string | 消息正文 |
| `messages[].timestamp` | string | 消息时间 |

**错误：**

| 状态码 | 说明 |
|--------|------|
| 404 | 客户不存在 |

---

### 2.2 发送客服消息

> POST `/api/chat/{customer_id}/send`

客服发送一条消息，后端保存后会自动调用 LLM 模拟客户回复。

**请求体：**

```json
{
  "content": "亲，M码红色有货的哦～"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `content` | string | 是 | 客服回复内容 |

**响应示例：**

```json
{
  "customer_message": "太好了！那我下单M码红色的，今天能发货吗？",
  "messages": [
    { "id": "...", "sender": "customer", "content": "...", "timestamp": "..." },
    { "id": "...", "sender": "agent", "content": "亲，M码红色有货的哦～", "timestamp": "..." },
    { "id": "...", "sender": "customer", "content": "太好了！那我下单M码红色的...", "timestamp": "..." }
  ],
  "is_handled": false
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `customer_message` | string | LLM 生成的客户回复内容（空字符串表示客户无回复） |
| `messages` | array | 更新后的完整聊天记录 |
| `is_handled` | boolean | 对话是否已结束（客户消息含 `[END]` 标记时置为 true） |

> **注意：** 该接口会调用 LLM，响应时间通常为 2-5 秒。前端建议使用乐观更新策略（先显示客服消息，再等响应刷新）。

**错误：**

| 状态码 | 说明 |
|--------|------|
| 404 | 客户不存在 |

---

## 3. 商品查询

### 3.1 搜索商品

> GET `/api/products`  
> GET `/api/products?search=关键词`

获取商品列表，支持关键词模糊搜索。搜索范围覆盖：商品名称、分类、描述、保修政策、退换政策、使用提示。

**请求参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `search` | string | 否 | 搜索关键词，留空返回全部商品 |

**响应示例：**

```json
[
  {
    "id": "P010",
    "name": "羽绒服",
    "price": 899.00,
    "stock": 15,
    "sizes": ["S", "M", "L", "XL"],
    "colors": ["黑色", "米白", "雾霾蓝"],
    "category": "女装",
    "description": "填充物为90%白鸭绒+10%羽片...蓬松度700+FP...可应对-15℃至5℃的寒冷天气...",
    "after_sales": {
      "warranty": "自签收之日起30天内，如出现严重钻绒（钻绒点>10处）、拉链损坏、面料撕裂等质量问题，免费换新或全额退款。",
      "return_policy": "支持7天无理由退换货，需保持商品整洁、吊牌完整、未洗涤。退回运费由买家承担（质量问题除外）。",
      "notes": "轻微钻绒属于羽绒制品正常现象...DWR防泼水效果会随洗涤次数逐渐减弱..."
    },
    "image_url": ""
  }
]
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 商品唯一 ID |
| `name` | string | 商品名称 |
| `price` | number | 售价（元） |
| `stock` | number | 当前库存数量 |
| `sizes` | array | 可选尺码 |
| `colors` | array | 可选颜色 |
| `category` | string | 商品分类（女装 / 鞋履 / 配饰 / 箱包 / 内衣家居） |
| `description` | string | 商品详细描述（面料、版型、尺码参考、洗涤保养等） |
| `after_sales.warranty` | string | 保修政策（保修范围、期限、处理方式） |
| `after_sales.return_policy` | string | 退换货政策（退换条件、运费承担方） |
| `after_sales.notes` | string | 使用/保养提示 |
| `image_url` | string | 商品图片 URL（预留） |

---

### 3.2 获取商品详情

> GET `/api/products/{product_id}`

根据 ID 获取单个商品详情。

**响应示例：**

同上 → 商品搜索 的单个元素结构。

**错误：**

| 状态码 | 说明 |
|--------|------|
| 404 | 商品不存在 |

---

## 4. 系统

### 4.1 重置所有会话

> POST `/api/reset`

清空所有客户的聊天记录，恢复到初始化状态（仅保留首条客户消息）。

**响应示例：**

```json
{
  "status": "ok",
  "message": "所有会话已重置"
}
```

---

## 附录

### 客户人设类型

| 客户 | 类型 | 特点 |
|------|------|------|
| 张三 | 售前咨询 | 对尺码、库存、搭配有疑问，语气友善 |
| 李四 | 售后投诉 | 商品质量有问题，要求退货退款 |
| 王五 | 投诉 | 情绪激动，商品有污渍和钻绒问题 |
| 赵六 | 售前咨询 | 想购买多件，询问搭配和库存 |
| 钱七 | 换货 | 尺码不合适要求换货，询问运费 |
| 孙八 | 垃圾广告 | 发布微信号引流，不理会客服回复 |
| 周九 | 售前/复购 | 老顾客回购，询问颜色和新品 |
| 吴十 | 物流查询 | 查询订单物流状态 |

### LLM 模拟客户规则

1. 客户始终以消费者身份说话，不跳出角色
2. 回复符合角色设定和情绪状态，保持一致性
3. 每次回复 1-3 句话，自然口语化
4. 问题解决后表达感谢，回复末尾加 `[END]` 标记对话结束
5. 投诉客户初始情绪激动，客服给出解决方案后逐渐缓和
6. 垃圾广告客户不理会客服回复，继续发广告
