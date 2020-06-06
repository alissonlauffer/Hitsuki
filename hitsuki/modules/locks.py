import html
from typing import Optional

from telegram import Message, Chat, ParseMode, User, MessageEntity
from telegram import TelegramError, ChatPermissions
from telegram.error import BadRequest
from telegram.ext import CommandHandler, MessageHandler, Filters
from telegram.ext.dispatcher import run_async
from telegram.utils.helpers import mention_html

from alphabet_detector import AlphabetDetector

import hitsuki.modules.sql.locks_sql as sql
from hitsuki import dispatcher, spamcheck, SUDO_USERS, LOGGER
from hitsuki.modules.disable import DisableAbleCommandHandler
from hitsuki.modules.helper_funcs.chat_status import can_delete, \
    is_user_admin, user_not_admin, user_admin, is_bot_admin
from hitsuki.modules.log_channel import loggable
from hitsuki.modules.warns import warn
from hitsuki.modules.connection import connected

from hitsuki.modules.languages import tl
from hitsuki.modules.helper_funcs.alternate import send_message

ad = AlphabetDetector()

LOCK_TYPES = {'audio': Filters.audio,
              'voice': Filters.voice,
              'document': Filters.document,
              'video': Filters.video,
              'contact': Filters.contact,
              'photo': Filters.photo,
              'url': Filters.entity(MessageEntity.URL) | Filters.caption_entity(MessageEntity.URL),
              'bots': Filters.status_update.new_chat_members,
              'forward': Filters.forwarded,
              'game': Filters.game,
              'location': Filters.location,
              'rtl': 'rtl',
              'button': 'button'
              }

LOCK_CHAT_RESTRICTION = {"all": {'can_send_messages': False, 'can_send_media_messages': False, 'can_send_polls': False,
                                 'can_send_other_messages': False, 'can_add_web_page_previews': False,
                                 'can_change_info': False, 'can_invite_users': False, 'can_pin_messages': False},
                         "messages": {'can_send_messages': False},
                         "media": {'can_send_media_messages': False},
                         "sticker": {'can_send_other_messages': False},
                         "gif": {'can_send_other_messages': False},
                         "poll": {'can_send_polls': False},
                         "other": {'can_send_other_messages': False},
                         "previews": {'can_add_web_page_previews': False},
                         "info": {'can_change_info': False},
                         "invite": {'can_invite_users': False},
                         "pin": {'can_pin_messages': False}}

UNLOCK_CHAT_RESTRICTION = {"all": {'can_send_messages': True, 'can_send_media_messages': True, 'can_send_polls': True,
                                   'can_send_other_messages': True, 'can_add_web_page_previews': True,
                                   'can_invite_users': True},
                           "messages": {'can_send_messages': True},
                           "media": {'can_send_media_messages': True},
                           "sticker": {'can_send_other_messages': True},
                           "gif": {'can_send_other_messages': True},
                           "poll": {'can_send_polls': True},
                           "other": {'can_send_other_messages': True},
                           "previews": {'can_add_web_page_previews': True},
                           "info": {'can_change_info': True},
                           "invite": {'can_invite_users': True},
                           "pin": {'can_pin_messages': True}}

PERM_GROUP = 1
REST_GROUP = 2


# NOT ASYNC
def restr_members(bot, chat_id, members, messages=False, media=False, other=False, previews=False):
    for mem in members:
        if mem.user in SUDO_USERS:
            pass
        try:
            bot.restrict_chat_member(chat_id, mem.user,
                                     can_send_messages=messages,
                                     can_send_media_messages=media,
                                     can_send_other_messages=other,
                                     can_add_web_page_previews=previews)
        except TelegramError:
            pass


# NOT ASYNC
def unrestr_members(bot, chat_id, members, messages=True, media=True, other=True, previews=True):
    for mem in members:
        try:
            bot.restrict_chat_member(chat_id, mem.user,
                                     can_send_messages=messages,
                                     can_send_media_messages=media,
                                     can_send_other_messages=other,
                                     can_add_web_page_previews=previews)
        except TelegramError:
            pass


@run_async
@spamcheck
def locktypes(update, context):
    locklist = list(LOCK_TYPES)
    locklist.sort()
    perm = list(LOCK_CHAT_RESTRICTION)
    perm.sort()
    send_message(update.effective_message, "\n - ".join(
        [tl(update.effective_message, "*Jenis kunci yang tersedia adalah:* ")] + locklist) + "\n\n" + "\n - ".join(
        [tl(update.effective_message, "*Jenis izin kunci yang tersedia adalah:* ")] + perm), parse_mode="markdown")


@user_admin
@spamcheck
@loggable
def lock(update, context) -> str:
    args = context.args
    chat = update.effective_chat  # type: Optional[Chat]
    user = update.effective_user  # type: Optional[User]

    if can_delete(chat, context.bot.id) or update.effective_message.chat.type == "private":
        if len(args) >= 1:
            ltype = args[0].lower()
            if ltype in LOCK_TYPES:
                # Connection check
                conn = connected(context.bot, update, chat, user.id, need_admin=True)
                if conn:
                    chat = dispatcher.bot.getChat(conn)
                    chat_id = conn
                    chat_name = chat.title
                    text = tl(update.effective_message, "Terkunci pesan *{}* untuk semua non-admin pada *{}*!").format(
                        ltype, chat_name)
                else:
                    if update.effective_message.chat.type == "private":
                        send_message(update.effective_message, tl(update.effective_message,
                                                                  "Anda bisa lakukan command ini pada grup, bukan pada PM"))
                        return ""
                    chat = update.effective_chat
                    chat_id = update.effective_chat.id
                    chat_name = update.effective_message.chat.title
                    text = tl(update.effective_message, "Terkunci pesan *{}* untuk semua non-admin!").format(ltype)
                sql.update_lock(chat.id, ltype, locked=True)
                send_message(update.effective_message, text, parse_mode="markdown")

                return "<b>{}:</b>" \
                       "\n#LOCK" \
                       "\n<b>Admin:</b> {}" \
                       "\nLocked <code>{}</code>.".format(html.escape(chat.title),
                                                          mention_html(user.id, user.first_name), ltype)

            elif ltype in LOCK_CHAT_RESTRICTION:
                # Connection check
                conn = connected(context.bot, update, chat, user.id, need_admin=True)
                if conn:
                    chat = dispatcher.bot.getChat(conn)
                    chat_id = conn
                    chat_name = chat.title
                    text = tl(update.effective_message,
                              "Izin terkunci pesan *{}* untuk semua non-admin pada *{}*!").format(ltype, chat_name)
                else:
                    if update.effective_message.chat.type == "private":
                        send_message(update.effective_message, tl(update.effective_message,
                                                                  "Anda bisa lakukan command ini pada grup, bukan pada PM"))
                        return ""
                    chat = update.effective_chat
                    chat_id = update.effective_chat.id
                    chat_name = update.effective_message.chat.title
                    text = tl(update.effective_message, "Izin terkunci pesan *{}* untuk semua non-admin!").format(ltype)

                current_permission = context.bot.getChat(chat_id).permissions
                context.bot.set_chat_permissions(chat_id=chat_id,
                                                 permissions=get_permission_list(eval(str(current_permission)),
                                                                                 LOCK_CHAT_RESTRICTION[ltype.lower()]))

                send_message(update.effective_message, text, parse_mode="markdown")
                return "<b>{}:</b>" \
                       "\n#Permission_LOCK" \
                       "\n<b>Admin:</b> {}" \
                       "\nLocked <code>{}</code>.".format(html.escape(chat.title),
                                                          mention_html(user.id, user.first_name), ltype)

            else:
                send_message(update.effective_message, tl(update.effective_message,
                                                          "Apa yang Anda coba untuk kunci...? Coba /locktypes untuk daftar kunci yang dapat dikunci"))
        else:
            send_message(update.effective_message, tl(update.effective_message, "Apa yang Anda ingin kunci...?"))

    else:
        send_message(update.effective_message,
                     tl(update.effective_message, "Saya bukan admin, atau tidak punya hak menghapus."))

    return ""


@run_async
@spamcheck
@user_admin
@loggable
def unlock(update, context) -> str:
    args = context.args
    chat = update.effective_chat  # type: Optional[Chat]
    user = update.effective_user  # type: Optional[User]
    message = update.effective_message  # type: Optional[Message]
    if is_user_admin(chat, message.from_user.id):
        if len(args) >= 1:
            ltype = args[0].lower()
            if ltype in LOCK_TYPES:
                # Connection check
                conn = connected(context.bot, update, chat, user.id, need_admin=True)
                if conn:
                    chat = dispatcher.bot.getChat(conn)
                    chat_id = conn
                    chat_name = chat.title
                    text = tl(update.effective_message, "Tidak terkunci *{}* untuk semua orang pada *{}*!").format(
                        ltype, chat_name)
                else:
                    if update.effective_message.chat.type == "private":
                        send_message(update.effective_message, tl(update.effective_message,
                                                                  "Anda bisa lakukan command ini pada grup, bukan pada PM"))
                        return ""
                    chat = update.effective_chat
                    chat_id = update.effective_chat.id
                    chat_name = update.effective_message.chat.title
                    text = tl(update.effective_message, "Tidak terkunci *{}* untuk semua orang!").format(ltype)
                sql.update_lock(chat.id, ltype, locked=False)
                send_message(update.effective_message, text, parse_mode="markdown")
                return "<b>{}:</b>" \
                       "\n#UNLOCK" \
                       "\n<b>Admin:</b> {}" \
                       "\nUnlocked <code>{}</code>.".format(html.escape(chat.title),
                                                            mention_html(user.id, user.first_name), ltype)

            elif ltype in UNLOCK_CHAT_RESTRICTION:
                # Connection check
                conn = connected(context.bot, update, chat, user.id, need_admin=True)
                if conn:
                    chat = dispatcher.bot.getChat(conn)
                    chat_id = conn
                    chat_name = chat.title
                    text = tl(update.effective_message, "Izin tidak terkunci *{}* untuk semua orang pada *{}*!").format(
                        ltype, chat_name)
                else:
                    if update.effective_message.chat.type == "private":
                        send_message(update.effective_message, tl(update.effective_message,
                                                                  "Anda bisa lakukan command ini pada grup, bukan pada PM"))
                        return ""
                    chat = update.effective_chat
                    chat_id = update.effective_chat.id
                    chat_name = update.effective_message.chat.title
                    text = tl(update.effective_message, "Izin tidak terkunci *{}* untuk semua orang!").format(ltype)

                current_permission = context.bot.getChat(chat_id).permissions
                context.bot.set_chat_permissions(chat_id=chat_id,
                                                 permissions=get_permission_list(eval(str(current_permission)),
                                                                                 UNLOCK_CHAT_RESTRICTION[
                                                                                     ltype.lower()]))

                send_message(update.effective_message, text, parse_mode="markdown")

                return "<b>{}:</b>" \
                       "\n#UNLOCK" \
                       "\n<b>Admin:</b> {}" \
                       "\nUnlocked <code>{}</code>.".format(html.escape(chat.title),
                                                            mention_html(user.id, user.first_name), ltype)
            else:
                send_message(update.effective_message, tl(update.effective_message,
                                                          "Apa yang Anda coba untuk membuka kunci...? Coba /locktypes untuk daftar kunci yang dapat dikunci"))

        else:
            send_message(update.effective_message,
                         tl(update.effective_message, "Apa yang Anda coba untuk buka kunci...?"))

    return ""


@run_async
@user_not_admin
def del_lockables(update, context):
    chat = update.effective_chat  # type: Optional[Chat]
    message = update.effective_message  # type: Optional[Message]

    for lockable, filter in LOCK_TYPES.items():
        if lockable == "rtl":
            if sql.is_locked(chat.id, lockable) and can_delete(chat, context.bot.id):
                if message.caption:
                    check = ad.detect_alphabet(u'{}'.format(message.caption))
                    if 'ARABIC' in check:
                        try:
                            message.delete()
                        except BadRequest as excp:
                            if excp.message == "Message to delete not found":
                                pass
                            else:
                                LOGGER.exception("ERROR in lockables")
                        getconf = sql.get_lockconf(chat.id)
                        if getconf:
                            warn(update.effective_user, chat,
                                 tl(update.effective_message, "Mengirim 'Teks RTL' yang sedang di kunci saat ini"),
                                 message, update.effective_user, conn=False)
                        break
                if message.text:
                    check = ad.detect_alphabet(u'{}'.format(message.text))
                    if 'ARABIC' in check:
                        try:
                            message.delete()
                        except BadRequest as excp:
                            if excp.message == "Message to delete not found":
                                pass
                            else:
                                LOGGER.exception("ERROR in lockables")
                        getconf = sql.get_lockconf(chat.id)
                        if getconf:
                            warn(update.effective_user, chat,
                                 tl(update.effective_message, "Mengirim 'Teks RTL' yang sedang di kunci saat ini"),
                                 message, update.effective_user, conn=False)
                        break
            continue
        if lockable == "button":
            if sql.is_locked(chat.id, lockable) and can_delete(chat, context.bot.id):
                if message.reply_markup and message.reply_markup.inline_keyboard:
                    try:
                        message.delete()
                    except BadRequest as excp:
                        if excp.message == "Message to delete not found":
                            pass
                        else:
                            LOGGER.exception("ERROR in lockables")
                    getconf = sql.get_lockconf(chat.id)
                    if getconf:
                        warn(update.effective_user, chat,
                             tl(update.effective_message, "Mengirim 'Pesan Tombol' yang sedang di kunci saat ini"),
                             message, update.effective_user, conn=False)
                    break
            continue
        if filter(update) and sql.is_locked(chat.id, lockable) and can_delete(chat, context.bot.id):
            if lockable == "bots":
                new_members = update.effective_message.new_chat_members
                for new_mem in new_members:
                    if new_mem.is_bot:
                        if not is_bot_admin(chat, context.bot.id):
                            send_message(update.effective_message, tl(update.effective_message,
                                                                      "Saya melihat bot, dan saya diberitahu untuk menghentikan mereka bergabung... "
                                                                      "tapi saya bukan admin!"))
                            return

                        chat.kick_member(new_mem.id)
                        send_message(update.effective_message, tl(update.effective_message,
                                                                  "Hanya admin yang diizinkan menambahkan bot ke obrolan ini! Keluar dari sini!"))
                        getconf = sql.get_lockconf(chat.id)
                        if getconf:
                            warn(update.effective_user, chat,
                                 tl(update.effective_message, "Memasukan 'Bot' yang sedang di kunci saat ini"), message,
                                 update.effective_user, conn=False)
                        break
            else:
                try:
                    message.delete()
                except BadRequest as excp:
                    if excp.message == "Message to delete not found":
                        pass
                    else:
                        LOGGER.exception("ERROR in lockables")
                getconf = sql.get_lockconf(chat.id)
                if getconf:
                    warn(update.effective_user, chat,
                         tl(update.effective_message, "Mengirim '{}' yang sedang di kunci saat ini").format(lockable),
                         message, update.effective_user, conn=False)

                break


def build_lock_message(chat_id):
    locks = sql.get_locks(chat_id)
    res = ""
    locklist = []
    permslist = []
    if locks:
        res += "*" + tl(chat_id, "Ini adalah kunci dalam obrolan ini:") + "*"
        if locks:
            locklist.append("sticker = `{}`".format(locks.sticker))
            locklist.append("audio = `{}`".format(locks.audio))
            locklist.append("voice = `{}`".format(locks.voice))
            locklist.append("document = `{}`".format(locks.document))
            locklist.append("video = `{}`".format(locks.video))
            locklist.append("contact = `{}`".format(locks.contact))
            locklist.append("photo = `{}`".format(locks.photo))
            locklist.append("gif = `{}`".format(locks.gif))
            locklist.append("url = `{}`".format(locks.url))
            locklist.append("bots = `{}`".format(locks.bots))
            locklist.append("forward = `{}`".format(locks.forward))
            locklist.append("game = `{}`".format(locks.game))
            locklist.append("location = `{}`".format(locks.location))
            locklist.append("rtl = `{}`".format(locks.rtl))
            locklist.append("button = `{}`".format(locks.button))
    permissions = dispatcher.bot.get_chat(chat_id).permissions
    permslist.append("messages = `{}`".format(permissions.can_send_messages))
    permslist.append("media = `{}`".format(permissions.can_send_media_messages))
    permslist.append("poll = `{}`".format(permissions.can_send_polls))
    permslist.append("other = `{}`".format(permissions.can_send_other_messages))
    permslist.append("previews = `{}`".format(permissions.can_add_web_page_previews))
    permslist.append("info = `{}`".format(permissions.can_change_info))
    permslist.append("invite = `{}`".format(permissions.can_invite_users))
    permslist.append("pin = `{}`".format(permissions.can_pin_messages))

    if locklist:
        # Ordering lock list
        locklist.sort()
        # Building lock list string
        for x in locklist:
            res += "\n - {}".format(x)
    res += "\n\n*" + tl(chat_id, "Ini adalah izin dalam obrolan ini:") + "*"
    for x in permslist:
        res += "\n - {}".format(x)
    return res


@run_async
@spamcheck
@user_admin
def list_locks(update, context):
    chat = update.effective_chat  # type: Optional[Chat]
    user = update.effective_user

    # Connection check
    conn = connected(context.bot, update, chat, user.id, need_admin=True)
    if conn:
        chat = dispatcher.bot.getChat(conn)
        chat_id = conn
        chat_name = chat.title
    else:
        if update.effective_message.chat.type == "private":
            send_message(update.effective_message,
                         tl(update.effective_message, "Anda bisa lakukan command ini pada grup, bukan pada PM"))
            return ""
        chat = update.effective_chat
        chat_id = update.effective_chat.id
        chat_name = update.effective_message.chat.title

    res = build_lock_message(chat.id)
    if conn:
        res = res.replace(tl(update.effective_message, 'obrolan ini'), '*{}*'.format(chat_name))

    send_message(update.effective_message, res, parse_mode=ParseMode.MARKDOWN)


@run_async
@spamcheck
def lock_warns(update, context):
    args = context.args
    chat = update.effective_chat  # type: Optional[Chat]
    user = update.effective_user

    # Connection check
    conn = connected(context.bot, update, chat, user.id, need_admin=True)
    if conn:
        chat = dispatcher.bot.getChat(conn)
        chat_id = conn
        chat_name = chat.title
    else:
        if update.effective_message.chat.type == "private":
            send_message(update.effective_message,
                         tl(update.effective_message, "Anda bisa lakukan command ini pada grup, bukan pada PM"))
            return ""
        chat = update.effective_chat
        chat_id = update.effective_chat.id
        chat_name = update.effective_message.chat.title

    if args:
        if args[0] == "on" or args[0] == "yes":
            sql.set_lockconf(chat_id, True)
            try:
                send_message(update.effective_message, tl(update.effective_message,
                                                          "Saya *akan* memperingati pengguna jika dia mengirim pesan yang dikunci"),
                             parse_mode="markdown")
            except BadRequest:
                send_message(update.effective_message, tl(update.effective_message,
                                                          "Saya *akan* memperingati pengguna jika dia mengirim pesan yang dikunci",
                                                          parse_mode="markdown", quote=False))
        elif args[0] == "off" or args[0] == "no":
            sql.set_lockconf(chat_id, False)
            try:
                send_message(update.effective_message, tl(update.effective_message,
                                                          "Saya *tidak akan* memperingati pengguna jika dia mengirim pesan yang dikunci"),
                             parse_mode="markdown")
            except BadRequest:
                send_message(update.effective_message, tl(update.effective_message,
                                                          "Saya *tidak akan* memperingati pengguna jika dia mengirim pesan yang dikunci",
                                                          parse_mode="markdown", quote=False))
        else:
            try:
                send_message(update.effective_message,
                             tl(update.effective_message, "Saya hanya mengerti 'on/yes' atau 'off/no' saja!"),
                             parse_mode="markdown")
            except BadRequest:
                send_message(update.effective_message,
                             tl(update.effective_message, "Saya hanya mengerti 'on/yes' atau 'off/no' saja!"),
                             parse_mode="markdown", quote=False)
    else:
        getconf = sql.get_lockconf(chat_id)
        if getconf:
            try:
                send_message(update.effective_message, tl(update.effective_message,
                                                          "Saat ini saya *akan* memperingati pengguna jika dia mengirim pesan yang dikunci"),
                             parse_mode="markdown")
            except BadRequest:
                send_message(update.effective_message, tl(update.effective_message,
                                                          "Saat ini saya *akan* memperingati pengguna jika dia mengirim pesan yang dikunci"),
                             parse_mode="markdown", quote=False)
        else:
            try:
                send_message(update.effective_message, tl(update.effective_message,
                                                          "Saat ini saya *tidak akan* memperingati pengguna jika dia mengirim pesan yang dikunci"),
                             parse_mode="markdown")
            except BadRequest:
                send_message(update.effective_message, tl(update.effective_message,
                                                          "Saat ini saya *tidak akan* memperingati pengguna jika dia mengirim pesan yang dikunci"),
                             parse_mode="markdown", quote=False)


def get_permission_list(current, new):
    permissions = {'can_send_messages': None, 'can_send_media_messages': None, 'can_send_polls': None,
                   'can_send_other_messages': None, 'can_add_web_page_previews': None,
                   'can_change_info': None, 'can_invite_users': None, 'can_pin_messages': None}
    permissions.update(current)
    permissions.update(new)
    new_permissions = ChatPermissions(**permissions)
    return new_permissions


def __import_data__(chat_id, data):
    # set chat locks
    locks = data.get('locks', {})
    for itemlock in locks:
        if itemlock in LOCK_TYPES:
            sql.update_lock(chat_id, itemlock, locked=True)
        elif itemlock in LOCK_CHAT_RESTRICTION:
            sql.update_restriction(chat_id, itemlock, locked=True)
        else:
            pass


def __migrate__(old_chat_id, new_chat_id):
    sql.migrate_chat(old_chat_id, new_chat_id)


def __chat_settings__(chat_id, user_id):
    return build_lock_message(chat_id)


__help__ = "locks_help"

__mod_name__ = "Locks"

LOCKTYPES_HANDLER = DisableAbleCommandHandler("locktypes", locktypes)
LOCK_HANDLER = CommandHandler("lock", lock, pass_args=True)  # , filters=Filters.group)
UNLOCK_HANDLER = CommandHandler("unlock", unlock, pass_args=True)  # , filters=Filters.group)
LOCKED_HANDLER = CommandHandler("locks", list_locks)  # , filters=Filters.group)
LOCKWARNS_HANDLER = CommandHandler("lockwarns", lock_warns, pass_args=True)

dispatcher.add_handler(LOCK_HANDLER)
dispatcher.add_handler(UNLOCK_HANDLER)
dispatcher.add_handler(LOCKTYPES_HANDLER)
dispatcher.add_handler(LOCKED_HANDLER)
dispatcher.add_handler(LOCKWARNS_HANDLER)

dispatcher.add_handler(MessageHandler(Filters.all & Filters.group, del_lockables), PERM_GROUP)
