/**
 * Terms of Use and Privacy Notice, in both UI languages.
 *
 * TEMPLATE: written for a New Zealand travel service under the Privacy Act 2020, the Consumer Guarantees Act 1993
 * and the Fair Trading Act 1986. It is a starting point, not legal advice. Have a qualified New Zealand lawyer review
 * and complete it (company name, address, Privacy Officer) before launch, and bump TERMS_VERSION in
 * backend/app/auth.py whenever it changes materially so every traveler accepts the new version.
 */
import type { Lang } from './language.ts';

export interface LegalSection { heading: string; paragraphs: string[] }
export interface LegalDocument { title: string; updated: string; template: string; sections: LegalSection[] }
type Bilingual = Record<Lang, LegalDocument>;

const TEMPLATE = {
  en: 'Template for review: this text has not yet been checked by a lawyer. Details in [brackets] are still to be filled in.',
  zh: '待审阅模板：本文尚未经过律师审核，方括号 [ ] 中的内容待补充。',
};

export const TERMS: Bilingual = {
  en: {
    title: 'Terms of Use', updated: 'Version 2026-10', template: TEMPLATE.en,
    sections: [
      { heading: 'Who we are', paragraphs: ['CareTrip is operated by [Company name], [address], New Zealand ("we"). These terms apply when you use CareTrip to plan or book travel within New Zealand.'] },
      { heading: 'What CareTrip does', paragraphs: [
        'We help you describe a trip, compare offers from travel suppliers, check their accessibility claims against independent sources, and book the offer you approve.',
        'Draft itineraries are illustrative suggestions. Opening hours, travel times and facilities can change, so please confirm anything that matters for your health or safety with the provider.',
        'Accessibility checks reduce risk but cannot guarantee every detail of a supplier\'s facilities. A travel advisor reviews offers whose evidence is unclear.'] },
      { heading: 'Booking and payment', paragraphs: [
        'Nothing is booked until you, the traveler, approve a specific offer and price. Family members you invite can help plan but cannot approve or pay.',
        'Your card is authorized when you approve and charged only after the supplier confirms the booking. If the booking cannot be completed, the authorization is released.',
        'Card details are handled by our payment provider (Stripe). CareTrip never sees or stores your card number.'] },
      { heading: 'Cancellations and refunds', paragraphs: [
        'Each offer shows its own cancellation rules before you approve it. Refunds follow those rules and go back to the original card.',
        'Your rights under the Consumer Guarantees Act 1993 and the Fair Trading Act 1986 are not affected by these terms.'] },
      { heading: 'Your account', paragraphs: [
        'You sign in with a code sent to your email. For approving payments, cancelling bookings or deleting your account, we ask for a fresh code to make sure it is really you.',
        'You can download your data or delete your account at any time from the Account page.'] },
      { heading: 'Suppliers', paragraphs: ['Accommodation and transport are provided by independent suppliers, whose own terms also apply to your stay or journey. We act as your booking agent.'] },
      { heading: 'Changes and contact', paragraphs: [
        'If these terms change materially, we will ask you to accept the new version the next time you sign in.',
        'Questions: [support email] · [phone].'] },
    ],
  },
  zh: {
    title: '使用条款', updated: '版本 2026-10', template: TEMPLATE.zh,
    sections: [
      { heading: '我们是谁', paragraphs: ['CareTrip 由 [公司名称]（地址：[地址]，新西兰）运营（下称"我们"）。当你使用 CareTrip 规划或预订新西兰境内旅行时，适用本条款。'] },
      { heading: 'CareTrip 提供什么服务', paragraphs: [
        '我们帮助你描述行程、比较旅行供应商的报价、用独立来源核对其无障碍说明，并预订你批准的报价。',
        '行程草稿仅供参考。开放时间、交通时间和设施可能变化，涉及健康或安全的事项请向服务方再次确认。',
        '无障碍核验可以降低风险，但无法保证供应商设施的每一个细节。证据不明确的报价会由旅行顾问人工审核。'] },
      { heading: '预订与付款', paragraphs: [
        '只有在你（出行人）批准具体报价和价格后才会预订。你邀请的家人可以帮忙规划，但不能批准或付款。',
        '批准时会先冻结银行卡金额，供应商确认预订后才会实际扣款。如果预订无法完成，冻结的金额会被释放。',
        '银行卡信息由我们的支付服务商（Stripe）处理，CareTrip 不会看到或保存你的卡号。'] },
      { heading: '取消与退款', paragraphs: [
        '每个报价在你批准前都会显示其取消规则，退款按该规则退回原银行卡。',
        '本条款不影响你依据《1993 年消费者保障法》和《1986 年公平交易法》享有的权利。'] },
      { heading: '你的账户', paragraphs: [
        '你通过邮箱验证码登录。在批准付款、取消预订或删除账户时，我们会要求输入新的验证码，确认是你本人操作。',
        '你可以随时在"账户"页面下载自己的数据或删除账户。'] },
      { heading: '供应商', paragraphs: ['住宿和交通由独立供应商提供，其自身条款同样适用于你的住宿或行程。我们作为你的预订代理。'] },
      { heading: '变更与联系方式', paragraphs: [
        '如果本条款发生重大变更，你下次登录时我们会请你接受新版本。',
        '如有疑问：[客服邮箱] · [电话]。'] },
    ],
  },
};

export const PRIVACY: Bilingual = {
  en: {
    title: 'Privacy Notice', updated: 'Version 2026-10', template: TEMPLATE.en,
    sections: [
      { heading: 'What we collect', paragraphs: [
        'Your email address and name; the trips you describe, including messages to the travel guide; offers, approvals, bookings and refund amounts; and basic technical logs.',
        'Only if you agree separately: health and access needs (such as wheelchair use, walking distance, dietary or medical notes) and an emergency contact.'] },
      { heading: 'Why we use it', paragraphs: ['To plan and book your trips, check accessibility, let family members you invite follow along, send booking emails, keep our service secure, and meet legal and accounting duties.'] },
      { heading: 'Who we share it with', paragraphs: [
        'Travel suppliers receive what they need to hold and book your trip. Stripe processes payments. Our email provider sends sign-in codes and booking emails.',
        'When AI planning is switched on, the text of your trip request is sent to the AI model provider ([Google Gemini / OpenAI]) to draft the plan, with access needs such as walking distance as planning hints but never your name, email, medical notes or emergency contact.',
        'We do not sell personal information.'] },
      { heading: 'How long we keep it', paragraphs: ['Account and trip data are kept while your account is open. Booking and payment records are kept for [7] years for tax and accounting. When you delete your account, your personal text is removed and the remaining booking records are anonymized.'] },
      { heading: 'Your rights', paragraphs: [
        'Under the Privacy Act 2020 you can ask to see and correct your information. From the Account page you can download everything we hold about you, withdraw consent for health details (which erases them), or delete your account.',
        'Privacy Officer: [name], [email]. If you are not satisfied with our response, you can complain to the Office of the Privacy Commissioner (privacy.org.nz).'] },
      { heading: 'Security', paragraphs: ['Sign-in uses one-time codes and secure cookies; sensitive actions need a fresh code; data is stored in [New Zealand / region] with access limited to staff who need it.'] },
    ],
  },
  zh: {
    title: '隐私声明', updated: '版本 2026-10', template: TEMPLATE.zh,
    sections: [
      { heading: '我们收集哪些信息', paragraphs: [
        '你的邮箱和姓名；你描述的行程（包括与旅行向导的对话）；报价、批准、预订和退款金额；以及基本的技术日志。',
        '仅在你另行同意时收集：健康与出行需求（如是否使用轮椅、步行距离、饮食或医疗备注）以及紧急联系人。'] },
      { heading: '我们为什么使用这些信息', paragraphs: ['用于规划和预订行程、核验无障碍条件、让你邀请的家人跟进行程、发送预订邮件、保障服务安全，以及履行法律和会计义务。'] },
      { heading: '我们与谁共享', paragraphs: [
        '旅行供应商会收到保留和预订行程所需的信息；Stripe 处理付款；邮件服务商发送登录验证码和预订邮件。',
        '启用 AI 规划时，你的行程需求文字会发送给 AI 模型服务商（[Google Gemini / OpenAI]）来起草计划；步行距离等出行需求会作为规划提示一并发送，但绝不会发送你的姓名、邮箱、医疗备注或紧急联系人。',
        '我们不会出售个人信息。'] },
      { heading: '保存多久', paragraphs: ['账户和行程数据在账户存续期间保存。预订和付款记录出于税务和会计要求保存 [7] 年。删除账户后，你的个人文字内容会被清除，剩余的预订记录会做匿名化处理。'] },
      { heading: '你的权利', paragraphs: [
        '根据《2020 年隐私法》，你有权查看和更正自己的信息。在"账户"页面，你可以下载我们保存的全部个人数据、撤回对健康信息的同意（相关信息会被删除），或删除账户。',
        '隐私负责人：[姓名]，[邮箱]。如果对我们的答复不满意，可以向新西兰隐私专员办公室（privacy.org.nz）投诉。'] },
      { heading: '安全措施', paragraphs: ['登录使用一次性验证码和安全 Cookie；敏感操作需要新的验证码；数据存储在 [新西兰 / 地区]，只有需要的工作人员才能访问。'] },
    ],
  },
};
