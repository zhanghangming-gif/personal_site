import {
  Heart,
  Flag,
  Loader2,
  MessageCircle,
  Pin,
  RefreshCw,
  Reply,
  ShieldCheck,
  Send,
  Trash2,
  X,
} from 'lucide-react';
import { FormEvent, useCallback, useEffect, useState } from 'react';
import { useToast } from '../components/Toast';
import {
  clearDemoMessages,
  getMessages,
  submitMessage,
  submitReply,
  toggleLike,
  reportContent,
} from '../services/messageService';
import {
  getIdentity,
  readSavedIdentity,
  requestEmailCode,
  saveIdentity,
  verifyEmailCode,
} from '../services/identityService';
import { isDemoMode } from '../services/api';
import type { GuestIdentity, Message, MessagePayload, ReplyPayload } from '../types';
import { useLanguage } from '../context/LanguageContext';
import { useSound } from '../hooks/useSound';

const emptyForm: MessagePayload = { nickname: '', email: '', content: '', website: '' };
const emptyReply: ReplyPayload = { nickname: '', content: '', website: '' };

export default function MessagesPage({ embedded = false }: { embedded?: boolean }) {
  const { language } = useLanguage();
  const en = language === 'en';
  const [form, setForm] = useState(emptyForm);
  const [identity, setIdentity] = useState<GuestIdentity>(() => readSavedIdentity());
  const [code, setCode] = useState('');
  const [codeSent, setCodeSent] = useState(false);
  const [identityBusy, setIdentityBusy] = useState(false);
  const [items, setItems] = useState<Message[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [replyingTo, setReplyingTo] = useState<string | null>(null);
  const [replyForm, setReplyForm] = useState(emptyReply);
  const [replySubmitting, setReplySubmitting] = useState(false);
  const [liking, setLiking] = useState<string | null>(null);
  const toast = useToast();
  const { play } = useSound();

  const load = useCallback(async (target = 1, append = false) => {
    setLoading(true);
    setError('');
    try {
      const result = await getMessages(target);
      setItems((current) => (append ? [...current, ...result.items] : result.items));
      setPage(result.page);
      setTotal(result.total);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : (en ? 'Failed to load messages' : '留言加载失败'));
    } finally {
      setLoading(false);
    }
  }, [en]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setForm((current) => ({
      ...current,
      nickname: identity.nickname,
      email: identity.email,
    }));
    setReplyForm((current) => ({ ...current, nickname: identity.nickname }));
  }, []);

  useEffect(() => {
    const email = (form.email || '').trim().toLowerCase();
    const saved = readSavedIdentity();
    if (!email || email !== saved.email.toLowerCase()) {
      setIdentity((current) => ({ ...current, email, verified: false }));
      setCodeSent(false);
      return;
    }
    setIdentity(saved);
  }, [form.email]);

  useEffect(() => {
    const email = (form.email || '').trim().toLowerCase();
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return;
    const timer = window.setTimeout(() => {
      void getIdentity(email)
        .then((result) => {
          setIdentity((current) => ({ ...current, email, verified: result.verified }));
          if (result.verified) {
            saveIdentity({
              nickname: form.nickname.trim() || result.nickname || identity.nickname,
              email,
              verified: true,
              remember: identity.remember,
            });
          }
        })
        .catch(() => undefined);
    }, 500);
    return () => window.clearTimeout(timer);
  }, [form.email, form.nickname, identity.nickname, identity.remember]);

  const validate = () => {
    if (form.nickname.trim().length < 2 || form.nickname.trim().length > 20)
      return en ? 'Nickname must be 2–20 characters' : '昵称需要 2 至 20 个字符';
    if (form.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email))
      return en ? 'Please enter a valid email address' : '请输入有效邮箱';
    if (form.content.trim().length < 5 || form.content.trim().length > 500)
      return en ? 'Message must be 5–500 characters' : '留言需要 5 至 500 个字符';
    return '';
  };

  const updateRememberedIdentity = (next: Partial<GuestIdentity>) => {
    const updated = {
      nickname: form.nickname.trim(),
      email: (form.email || '').trim().toLowerCase(),
      verified: identity.verified,
      remember: identity.remember,
      ...next,
    };
    setIdentity(updated);
    saveIdentity(updated);
  };

  const sendCode = async () => {
    const email = (form.email || '').trim().toLowerCase();
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email))
      return toast(en ? 'Please enter a valid email first' : '请先输入有效邮箱', 'error');
    setIdentityBusy(true);
    try {
      const message = await requestEmailCode(email);
      setCodeSent(true);
      toast(message);
    } catch (caught) {
      toast(caught instanceof Error ? caught.message : (en ? 'Failed to send code' : '验证码发送失败'), 'error');
    } finally {
      setIdentityBusy(false);
    }
  };

  const verifyCode = async () => {
    const email = (form.email || '').trim().toLowerCase();
    if (!email || !code.trim()) return toast(en ? 'Enter email and code first' : '请先输入邮箱和验证码', 'error');
    setIdentityBusy(true);
    try {
      const message = await verifyEmailCode(email, code.trim(), form.nickname.trim());
      updateRememberedIdentity({ email, verified: true });
      setCode('');
      setCodeSent(false);
      toast(message);
    } catch (caught) {
      toast(caught instanceof Error ? caught.message : (en ? 'Verification failed' : '验证失败'), 'error');
    } finally {
      setIdentityBusy(false);
    }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const validationMessage = validate();
    if (validationMessage) return toast(validationMessage, 'error');
    const last = Number(sessionStorage.getItem('zhm-last-submit') || 0);
    if (Date.now() - last < 10000) return toast(en ? 'Please wait before submitting again' : '提交得有点快，请稍后再试', 'error');
    setSubmitting(true);
    try {
      const result = await submitMessage({
        ...form,
        nickname: form.nickname.trim(),
        email: (form.email || '').trim().toLowerCase(),
        content: form.content.trim(),
      });
      sessionStorage.setItem('zhm-last-submit', String(Date.now()));
      updateRememberedIdentity({});
      setForm((current) => ({ ...current, content: '', website: '' }));
      toast(result);
      await load();
    } catch (caught) {
      toast(caught instanceof Error ? caught.message : (en ? 'Submission failed. Please try again.' : '提交失败，请稍后重试'), 'error');
    } finally {
      setSubmitting(false);
    }
  };

  const openReply = (messageId: string) => {
    if (replyingTo === messageId) {
      play('panelClose');
      setReplyingTo(null);
      return;
    }
    play('panelOpen');
    setReplyingTo(messageId);
    setReplyForm((current) => ({ ...emptyReply, nickname: current.nickname }));
  };

  const publishReply = async (event: FormEvent, messageId: string) => {
    event.preventDefault();
    const nickname = replyForm.nickname.trim();
    const content = replyForm.content.trim();
    if (nickname.length < 2 || nickname.length > 20)
      return toast(en ? 'Nickname must be 2–20 characters' : '昵称需要 2 至 20 个字符', 'error');
    if (content.length < 2 || content.length > 300)
      return toast(en ? 'Reply must be 2–300 characters' : '回复需要 2 至 300 个字符', 'error');
    setReplySubmitting(true);
    try {
      const result = await submitReply(messageId, { ...replyForm, nickname, content });
      toast(result);
      setReplyingTo(null);
      setReplyForm({ ...emptyReply, nickname });
      await load();
    } catch (caught) {
      toast(caught instanceof Error ? caught.message : (en ? 'Reply failed. Please try again.' : '回复失败，请稍后重试'), 'error');
    } finally {
      setReplySubmitting(false);
    }
  };

  const like = async (entityType: 'message' | 'reply', entityId: string) => {
    if (liking) return;
    setLiking(entityId);
    try {
      const result = await toggleLike(entityType, entityId);
      setItems((current) =>
        current.map((message) => {
          if (entityType === 'message' && message.id === entityId) {
            return { ...message, ...result };
          }
          if (entityType === 'reply') {
            return {
              ...message,
              replies: message.replies.map((reply) =>
                reply.id === entityId ? { ...reply, ...result } : reply,
              ),
            };
          }
          return message;
        }),
      );
    } catch (caught) {
      toast(caught instanceof Error ? caught.message : (en ? 'Like failed. Please try again.' : '点赞失败，请稍后重试'), 'error');
    } finally {
      setLiking(null);
    }
  };

  const report = async (entityType: 'message' | 'reply', entityId: string) => {
    const reason = window.prompt(en ? 'Briefly describe the reason (e.g. spam, abuse, inappropriate content)' : '请简单说明举报原因（例如：广告、辱骂、不当内容）', en ? 'Inappropriate content' : '不当内容');
    if (!reason) return;
    try { toast(await reportContent(entityType, entityId, reason)); }
    catch (caught) { toast(caught instanceof Error ? caught.message : (en ? 'Report failed' : '举报失败'), 'error'); }
  };

  const clear = () => {
    clearDemoMessages();
    void load();
    toast(en ? 'Demo messages cleared' : '演示留言已清除');
  };

  return (
    <section
      id={embedded ? 'messages' : undefined}
      className={embedded ? 'section-pad scroll-mt-16' : 'pb-24 pt-32'}
    >
      <div className="container-site grid gap-10 lg:grid-cols-[.8fr_1.2fr]">
        <section>
          <p className="eyebrow">GUESTBOOK</p>
          <h1 className="title-xl">{en ? 'Leave a message' : '留下一句话'}</h1>
          <p className="mt-4 leading-8 text-slate-600 dark:text-slate-300">
            {en ? 'Share thoughts about technology, projects, or anything interesting. Your email is used only for replies and remains private.' : '欢迎交流技术、项目或任何有意思的想法。邮箱仅用于回复，不会公开。'}
          </p>
          <form className="surface mt-8 space-y-5 rounded-2xl p-6" onSubmit={submit} noValidate>
            <label className="block">
              <span className="mb-2 flex items-center justify-between gap-3 text-sm font-semibold">
                <span>{en ? 'Nickname *' : '昵称 *'}</span>
                {identity.verified && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs text-emerald-600 dark:text-emerald-300">
                    <ShieldCheck size={13} />
                    {en ? 'Verified' : '已验证'}
                  </span>
                )}
              </span>
              <input
                className="min-h-11 w-full rounded-xl border bg-transparent px-3"
                minLength={2}
                maxLength={20}
                value={form.nickname}
                autoComplete="nickname"
                onChange={(event) => {
                  setForm({ ...form, nickname: event.target.value });
                  setIdentity((current) => ({ ...current, nickname: event.target.value }));
                }}
              />
            </label>
            <label className="block">
              <span className="mb-2 block text-sm font-semibold">
                {en ? 'Email ' : '邮箱 '}<small className="font-normal text-slate-500">{en ? '(optional, private)' : '（选填，不公开）'}</small>
              </span>
              <input
                type="email"
                className="min-h-11 w-full rounded-xl border bg-transparent px-3"
                value={form.email || ''}
                autoComplete="email"
                onChange={(event) => setForm({ ...form, email: event.target.value })}
              />
            </label>
            {(form.email || '').trim() && (
              <div className="rounded-2xl border border-blue-500/15 bg-blue-500/[.035] p-3">
                <div className="flex flex-col gap-3 sm:flex-row">
                  <input
                    inputMode="numeric"
                    maxLength={6}
                    value={code}
                    onChange={(event) => setCode(event.target.value.replace(/\D/g, '').slice(0, 6))}
                    placeholder={en ? '6-digit code' : '6 位验证码'}
                    className="min-h-10 flex-1 rounded-xl border bg-[rgb(var(--surface))] px-3 text-sm"
                    disabled={identity.verified}
                  />
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => void sendCode()}
                      disabled={identityBusy || identity.verified}
                      className="button-secondary min-h-10 px-3 py-2 text-sm disabled:opacity-50"
                    >
                      {identityBusy && !codeSent ? <Loader2 className="animate-spin" size={15} /> : null}
                      {codeSent ? (en ? 'Resend' : '重新发送') : (en ? 'Send code' : '发送验证码')}
                    </button>
                    <button
                      type="button"
                      onClick={() => void verifyCode()}
                      disabled={identityBusy || identity.verified || code.length !== 6}
                      className="button-primary min-h-10 px-3 py-2 text-sm disabled:opacity-50"
                    >
                      {identityBusy && codeSent ? <Loader2 className="animate-spin" size={15} /> : null}
                      {en ? 'Verify' : '验证'}
                    </button>
                  </div>
                </div>
                <p className="mt-2 text-xs leading-5 text-slate-500">
                  {identity.verified
                    ? en
                      ? 'This browser has verified this email. Future messages can use the same identity.'
                      : '这个浏览器已验证该邮箱，之后留言会沿用这个身份。'
                    : en
                      ? 'Verification is optional. It marks your public message as verified and helps keep your nickname consistent.'
                      : '邮箱验证是可选的。验证后公开留言会显示已验证，也方便固定你的昵称身份。'}
                </p>
              </div>
            )}
            <label className="block">
              <span className="mb-2 flex justify-between text-sm font-semibold">
                <span>{en ? 'Message *' : '留言内容 *'}</span>
                <span className="font-normal text-slate-500">{en ? `${500 - form.content.length} characters left` : `剩余 ${500 - form.content.length} 字`}</span>
              </span>
              <textarea
                className="min-h-36 w-full resize-y rounded-xl border bg-transparent p-3"
                minLength={5}
                maxLength={500}
                value={form.content}
                onChange={(event) => setForm({ ...form, content: event.target.value })}
              />
            </label>
            <label className="flex items-start gap-2 rounded-xl bg-slate-100/70 p-3 text-sm text-slate-600 dark:bg-slate-800/70 dark:text-slate-300">
              <input
                type="checkbox"
                checked={identity.remember}
                onChange={(event) => updateRememberedIdentity({ remember: event.target.checked })}
                className="mt-1"
              />
              <span>
                {en
                  ? 'Remember my nickname and email on this browser'
                  : '在这个浏览器记住我的昵称和邮箱'}
              </span>
            </label>
            <label className="absolute -left-[9999px]" aria-hidden="true">
              Website
              <input
                tabIndex={-1}
                autoComplete="off"
                value={form.website}
                onChange={(event) => setForm({ ...form, website: event.target.value })}
              />
            </label>
            <button disabled={submitting} className="button-primary w-full disabled:opacity-60">
              {submitting ? <Loader2 className="animate-spin" size={17} /> : <Send size={17} />}
              {submitting ? (en ? 'Submitting…' : '正在提交…') : (en ? 'Post message' : '提交留言')}
            </button>
            <p className="text-xs leading-6 text-slate-500">
              {en ? 'Do not include phone numbers, addresses, or other sensitive information. Messages are public plain text; emails are never shown.' : '请勿填写手机号、住址等敏感信息。留言以纯文本公开展示，邮箱不会出现在公开页面中。'}
            </p>
          </form>
        </section>

        <section>
          <div className="flex items-end justify-between gap-4">
            <div>
              <p className="eyebrow">PUBLIC MESSAGES</p>
              <h2 className="text-3xl font-bold">
                {en ? 'Public messages' : '公开留言'} <span className="text-base font-normal text-slate-500">{total}</span>
              </h2>
            </div>
            {isDemoMode && (
              <button onClick={clear} className="button-secondary px-3">
                <Trash2 size={16} />
                <span className="hidden sm:inline">{en ? 'Clear demo messages' : '清除演示留言'}</span>
              </button>
            )}
          </div>

          <div className="mt-8 space-y-4">
            {loading && !items.length ? (
              Array.from({ length: 3 }).map((_, index) => (
                <div key={index} className="surface animate-pulse rounded-2xl p-6">
                  <div className="h-4 w-24 rounded bg-slate-200 dark:bg-slate-700" />
                  <div className="mt-5 h-3 rounded bg-slate-200 dark:bg-slate-700" />
                  <div className="mt-2 h-3 w-2/3 rounded bg-slate-200 dark:bg-slate-700" />
                </div>
              ))
            ) : error ? (
              <div className="surface rounded-2xl p-8 text-center">
                <p className="text-red-500">{error}</p>
                <button onClick={() => void load()} className="button-secondary mt-5">
                  <RefreshCw size={16} /> {en ? 'Retry' : '重试'}
                </button>
              </div>
            ) : !items.length ? (
              <div className="surface grid min-h-72 place-items-center rounded-2xl text-center">
                <div>
                  <MessageCircle className="mx-auto mb-4 text-slate-400" size={42} />
                  <h3 className="font-bold">{en ? 'No public messages yet' : '还没有公开留言'}</h3>
                  <p className="mt-2 text-sm text-slate-500">{en ? 'Be the first to leave one.' : '来成为第一个留言的人吧。'}</p>
                </div>
              </div>
            ) : (
              items.map((item) => (
                <article className="surface rounded-2xl p-5 sm:p-6" key={item.id}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-bold">{item.nickname}</h3>
                      {item.emailVerified && (
                        <span className="inline-flex items-center gap-1 rounded-full border border-emerald-400/30 bg-emerald-500/10 px-2.5 py-1 text-xs font-semibold text-emerald-600 dark:text-emerald-300">
                          <ShieldCheck size={13} aria-hidden="true" />
                          {en ? 'Verified' : '已验证'}
                        </span>
                      )}
                      {item.pinned && (
                        <span className="inline-flex items-center gap-1 rounded-full border border-blue-400/30 bg-blue-500/10 px-2.5 py-1 text-xs font-semibold text-blue-600 dark:text-blue-300">
                          <Pin size={13} aria-hidden="true" />
                          {en ? 'Pinned' : '已置顶'}
                        </span>
                      )}
                    </div>
                    <time className="text-xs text-slate-500" dateTime={item.createdAt}>
                      {new Date(item.createdAt).toLocaleString(en ? 'en-US' : 'zh-CN')}
                    </time>
                  </div>
                  <p className="mt-4 whitespace-pre-wrap break-words text-sm leading-7 text-slate-600 dark:text-slate-300">
                    {item.content}
                  </p>
                  <div className="mt-4 flex items-center gap-2 border-t border-slate-200/70 pt-3 dark:border-slate-700/70">
                    <LikeButton
                      count={item.likeCount}
                      liked={item.liked}
                      disabled={liking === item.id}
                      onClick={() => void like('message', item.id)}
                    />
                    <button
                      type="button"
                      onClick={() => openReply(item.id)}
                      className="inline-flex min-h-9 items-center gap-1.5 rounded-lg px-3 text-sm font-medium text-slate-500 transition hover:bg-slate-100 hover:text-blue-600 dark:hover:bg-slate-800"
                    >
                      <Reply size={16} /> {en ? 'Reply' : '回复'}{item.replies.length ? ` ${item.replies.length}` : ''}
                    </button>
                    <button type="button" onClick={() => void report('message', item.id)} className="inline-flex min-h-9 items-center gap-1.5 rounded-lg px-3 text-sm font-medium text-slate-500 transition hover:bg-amber-500/10 hover:text-amber-600"><Flag size={15}/>{en ? 'Report' : '举报'}</button>
                  </div>

                  {item.replies.length > 0 && (
                    <div className="mt-4 space-y-3 border-l-2 border-blue-500/25 pl-3 sm:pl-4">
                      {item.replies.map((reply) => (
                        <div className="rounded-xl bg-slate-100/70 p-4 dark:bg-slate-800/55" key={reply.id}>
                          <div className="flex items-start justify-between gap-3">
                            <strong className="text-sm">{reply.nickname}</strong>
                            <time className="text-[11px] text-slate-500" dateTime={reply.createdAt}>
                              {new Date(reply.createdAt).toLocaleString(en ? 'en-US' : 'zh-CN')}
                            </time>
                          </div>
                          <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6 text-slate-600 dark:text-slate-300">
                            {reply.content}
                          </p>
                          <div className="mt-2">
                            <LikeButton
                              count={reply.likeCount}
                              liked={reply.liked}
                              disabled={liking === reply.id}
                              onClick={() => void like('reply', reply.id)}
                              compact
                            />
                            <button type="button" onClick={() => void report('reply', reply.id)} className="ml-2 inline-flex min-h-8 items-center gap-1 rounded-lg px-2 text-xs text-slate-500 hover:text-amber-600"><Flag size={13}/>{en ? 'Report' : '举报'}</button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {replyingTo === item.id && (
                    <form
                      className="mt-4 rounded-xl border border-blue-500/25 bg-blue-500/[.035] p-4"
                      onSubmit={(event) => void publishReply(event, item.id)}
                    >
                      <div className="mb-3 flex items-center justify-between">
                        <strong className="text-sm">{en ? `Reply to ${item.nickname}` : `回复 ${item.nickname}`}</strong>
                        <button
                          type="button"
                          className="rounded-md p-1 text-slate-500 hover:bg-slate-200 dark:hover:bg-slate-700"
                          onClick={() => {
                            play('panelClose');
                            setReplyingTo(null);
                          }}
                          data-sound-off="true"
                          aria-label={en ? 'Close reply form' : '关闭回复框'}
                        >
                          <X size={16} />
                        </button>
                      </div>
                      <div className="grid gap-3 sm:grid-cols-[9rem_1fr]">
                        <input
                          className="min-h-10 rounded-lg border bg-transparent px-3 text-sm"
                          placeholder={en ? 'Your nickname' : '你的昵称'}
                          maxLength={20}
                          value={replyForm.nickname}
                          onChange={(event) => setReplyForm({ ...replyForm, nickname: event.target.value })}
                        />
                        <textarea
                          className="min-h-20 resize-y rounded-lg border bg-transparent p-3 text-sm"
                          placeholder={en ? 'Write a reply…' : '写下回复…'}
                          maxLength={300}
                          value={replyForm.content}
                          onChange={(event) => setReplyForm({ ...replyForm, content: event.target.value })}
                        />
                      </div>
                      <label className="absolute -left-[9999px]" aria-hidden="true">
                        Website
                        <input
                          tabIndex={-1}
                          autoComplete="off"
                          value={replyForm.website}
                          onChange={(event) => setReplyForm({ ...replyForm, website: event.target.value })}
                        />
                      </label>
                      <div className="mt-3 flex justify-end">
                        <button
                          className="button-primary min-h-9 px-4 py-2 text-sm disabled:opacity-60"
                          disabled={replySubmitting}
                        >
                          {replySubmitting ? <Loader2 className="animate-spin" size={15} /> : <Send size={15} />}
                          {en ? 'Post reply' : '发布回复'}
                        </button>
                      </div>
                    </form>
                  )}
                </article>
              ))
            )}
            {items.length < total && (
              <button
                disabled={loading}
                onClick={() => void load(page + 1, true)}
                className="button-secondary w-full"
              >
                {loading ? <Loader2 className="animate-spin" size={16} /> : null} {en ? 'Load more' : '加载更多'}
              </button>
            )}
          </div>
        </section>
      </div>
    </section>
  );
}

function LikeButton({
  count,
  liked,
  disabled,
  onClick,
  compact = false,
}: {
  count: number;
  liked: boolean;
  disabled: boolean;
  onClick: () => void;
  compact?: boolean;
}) {
  const { language } = useLanguage();
  const en = language === 'en';
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      aria-label={liked ? (en ? 'Unlike' : '取消点赞') : (en ? 'Like' : '点赞')}
      aria-pressed={liked}
      className={`inline-flex items-center gap-1.5 rounded-lg font-medium transition disabled:opacity-50 ${
        compact ? 'min-h-8 px-2 text-xs' : 'min-h-9 px-3 text-sm'
      } ${
        liked
          ? 'bg-rose-500/10 text-rose-500'
          : 'text-slate-500 hover:bg-rose-500/10 hover:text-rose-500'
      }`}
    >
      <Heart size={compact ? 14 : 16} fill={liked ? 'currentColor' : 'none'} />
      {count > 0 ? count : (en ? 'Like' : '点赞')}
    </button>
  );
}
