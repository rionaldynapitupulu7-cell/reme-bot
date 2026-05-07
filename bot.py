import logging
import random
import string
import sqlite3
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# ===== KONFIGURASI =====
BOT_TOKEN = "8636129984:AAGEKsyFfNkefifZ3wurWTXPtff7IoczEK0"
OWNER_IDS = [8695568315]
ADMIN_IDS = [8695568315]
TAX_PERCENT = 3

ROULETTE = [0,32,15,19,4,21,2,25,17,34,6,27,13,36,11,30,8,23,10,5,24,16,33,1,20,14,31,9,22,18,29,7,28,12,35,3,26]
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

def init_db():
    conn = sqlite3.connect('reme_bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, username TEXT,
        saldo INTEGER DEFAULT 0, role TEXT DEFAULT 'member',
        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS rooms (
        room_id TEXT PRIMARY KEY, player1_id INTEGER, player2_id INTEGER,
        taruhan INTEGER, total_ronde INTEGER, ronde_sekarang INTEGER DEFAULT 1,
        skor1 INTEGER DEFAULT 0, skor2 INTEGER DEFAULT 0,
        spin1 INTEGER DEFAULT -1, spin2 INTEGER DEFAULT -1,
        status TEXT DEFAULT 'waiting', chat_id INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS topup (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
        jumlah INTEGER, status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS transaksi (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
        tipe TEXT, jumlah INTEGER, keterangan TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

def get_user(user_id, username=None):
    conn = sqlite3.connect('reme_bot.db')
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = c.fetchone()
    if not user:
        c.execute('INSERT INTO users (user_id, username, saldo, role) VALUES (?, ?, 0, "member")',
                  (user_id, username or str(user_id)))
        conn.commit()
        c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = c.fetchone()
    elif username and user[1] != username:
        c.execute('UPDATE users SET username = ? WHERE user_id = ?', (username, user_id))
        conn.commit()
    conn.close()
    return user

def get_saldo(user_id):
    conn = sqlite3.connect('reme_bot.db')
    c = conn.cursor()
    c.execute('SELECT saldo FROM users WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def get_role(user_id):
    if user_id in OWNER_IDS:
        return 'owner'
    conn = sqlite3.connect('reme_bot.db')
    c = conn.cursor()
    c.execute('SELECT role FROM users WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 'member'

def update_saldo(user_id, jumlah, tipe='game', keterangan=''):
    conn = sqlite3.connect('reme_bot.db')
    c = conn.cursor()
    c.execute('UPDATE users SET saldo = saldo + ? WHERE user_id = ?', (jumlah, user_id))
    c.execute('INSERT INTO transaksi (user_id, tipe, jumlah, keterangan) VALUES (?, ?, ?, ?)',
              (user_id, tipe, jumlah, keterangan))
    conn.commit()
    conn.close()

def set_saldo_db(user_id, jumlah, keterangan=''):
    conn = sqlite3.connect('reme_bot.db')
    c = conn.cursor()
    c.execute('UPDATE users SET saldo = ? WHERE user_id = ?', (jumlah, user_id))
    c.execute('INSERT INTO transaksi (user_id, tipe, jumlah, keterangan) VALUES (?, ?, ?, ?)',
              (user_id, 'set', jumlah, keterangan))
    conn.commit()
    conn.close()

def get_username(user_id):
    conn = sqlite3.connect('reme_bot.db')
    c = conn.cursor()
    c.execute('SELECT username FROM users WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else str(user_id)

def is_admin(user_id):
    return user_id in OWNER_IDS or user_id in ADMIN_IDS or get_role(user_id) in ['admin', 'owner']

def is_owner(user_id):
    return user_id in OWNER_IDS or get_role(user_id) == 'owner'

def get_target_from_reply_or_args(update, parts, arg_index=1):
    """
    Ambil target user_id dari reply pesan ATAU dari argumen command.
    Kembalikan (target_id, error_message).
    Jika pakai reply, arg_index tidak diperlukan di parts.
    """
    msg = update.message
    # Prioritas 1: reply ke pesan
    if msg.reply_to_message and msg.reply_to_message.from_user:
        target = msg.reply_to_message.from_user
        return target.id, None
    # Prioritas 2: argumen manual
    if len(parts) > arg_index:
        try:
            return int(parts[arg_index]), None
        except:
            return None, "❌ ID tidak valid!"
    return None, None  # Tidak ada target, caller tentukan pesan error

def generate_room_id():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))

def hitung_reme(angka):
    if angka <= 9:
        return angka
    total = sum(int(d) for d in str(angka))
    while total > 9:
        total = sum(int(d) for d in str(total))
    return total

def spin_roulette():
    return random.choice(ROULETTE)

def get_room_by_player(user_id):
    conn = sqlite3.connect('reme_bot.db')
    c = conn.cursor()
    c.execute('''SELECT * FROM rooms WHERE (player1_id = ? OR player2_id = ?)
                 AND status IN ("waiting", "playing")''', (user_id, user_id))
    room = c.fetchone()
    conn.close()
    return room

def get_room(room_id):
    conn = sqlite3.connect('reme_bot.db')
    c = conn.cursor()
    c.execute('SELECT * FROM rooms WHERE room_id = ?', (room_id,))
    room = c.fetchone()
    conn.close()
    return room

def update_room(room_id, **kwargs):
    conn = sqlite3.connect('reme_bot.db')
    c = conn.cursor()
    for key, val in kwargs.items():
        c.execute(f'UPDATE rooms SET {key} = ? WHERE room_id = ?', (val, room_id))
    conn.commit()
    conn.close()

def delete_room(room_id):
    conn = sqlite3.connect('reme_bot.db')
    c = conn.cursor()
    c.execute('DELETE FROM rooms WHERE room_id = ?', (room_id,))
    conn.commit()
    conn.close()

async def handle_reme(update, context):
    user = update.effective_user
    chat_id = update.effective_chat.id
    get_user(user.id, user.username or user.first_name)
    parts = update.message.text.strip().split()
    if len(parts) != 3:
        await update.message.reply_text("❌ Format: `.reme [taruhan] [ronde]`\nContoh: `.reme 5000 1r`", parse_mode='Markdown', reply_to_message_id=update.message.message_id)
        return
    try:
        taruhan = int(parts[1])
        total_ronde = int(parts[2].lower().replace('r', ''))
    except:
        await update.message.reply_text("❌ Format salah! Contoh: `.reme 5000 1r`", parse_mode='Markdown', reply_to_message_id=update.message.message_id)
        return
    if taruhan < 100:
        await update.message.reply_text("❌ Taruhan minimal 100!", parse_mode='Markdown', reply_to_message_id=update.message.message_id)
        return
    if total_ronde < 1 or total_ronde > 10:
        await update.message.reply_text("❌ Ronde harus 1-10!", parse_mode='Markdown', reply_to_message_id=update.message.message_id)
        return
    if get_room_by_player(user.id):
        await update.message.reply_text("❌ Kamu sudah di room lain!", parse_mode='Markdown', reply_to_message_id=update.message.message_id)
        return
    saldo = get_saldo(user.id)
    if saldo < taruhan:
        await update.message.reply_text(f"❌ Saldo tidak cukup!\nSaldo: *{saldo:,}* | Taruhan: *{taruhan:,}*\n\nTop up: `.topup [jumlah]`", parse_mode='Markdown', reply_to_message_id=update.message.message_id)
        return
    conn = sqlite3.connect('reme_bot.db')
    c = conn.cursor()
    c.execute('SELECT * FROM rooms WHERE status="waiting" AND taruhan=? AND total_ronde=? AND player2_id IS NULL AND chat_id=?',
              (taruhan, total_ronde, chat_id))
    waiting = c.fetchone()
    conn.close()
    if waiting:
        room_id = waiting[0]
        p1_id = waiting[1]
        if p1_id == user.id:
            await update.message.reply_text("❌ Kamu sudah buat room ini!", parse_mode='Markdown', reply_to_message_id=update.message.message_id)
            return
        update_saldo(user.id, -taruhan, 'taruhan', f'Reme room {room_id}')
        update_saldo(p1_id, -taruhan, 'taruhan', f'Reme room {room_id}')
        conn = sqlite3.connect('reme_bot.db')
        c = conn.cursor()
        c.execute('UPDATE rooms SET player2_id=?, status="playing" WHERE room_id=?', (user.id, room_id))
        conn.commit()
        conn.close()
        p1_user = get_username(p1_id)
        await update.message.reply_text(
            f"🎰 *Room Reme Dimulai!*\n• Room ID: `{room_id}`\n• Player 1: @{p1_user}\n• Player 2: @{user.username or user.first_name}\n• Taruhan: *{taruhan:,}*\n• Mode: *{total_ronde}r*\n\nKedua pemain ketik *.spinr* untuk mulai!",
            parse_mode='Markdown', reply_to_message_id=update.message.message_id)
    else:
        room_id = generate_room_id()
        conn = sqlite3.connect('reme_bot.db')
        c = conn.cursor()
        c.execute('INSERT INTO rooms (room_id,player1_id,taruhan,total_ronde,chat_id,status) VALUES (?,?,?,?,?,"waiting")',
                  (room_id, user.id, taruhan, total_ronde, chat_id))
        conn.commit()
        conn.close()
        await update.message.reply_text(
            f"🎰 *Room Reme Dibuat*\n• Room ID: `{room_id}`\n• PLAYER: @{user.username or user.first_name}\n• Taruhan: *{taruhan:,}*\n• Mode: *{total_ronde}r*\n\nPemain lain join: *.reme {taruhan} {total_ronde}r*",
            parse_mode='Markdown', reply_to_message_id=update.message.message_id)

async def handle_spinr(update, context):
    user = update.effective_user
    get_user(user.id, user.username or user.first_name)
    room = get_room_by_player(user.id)
    if not room:
        await update.message.reply_text("❌ Kamu tidak di room manapun!", parse_mode='Markdown', reply_to_message_id=update.message.message_id)
        return
    room_id,p1_id,p2_id,taruhan,total_ronde,ronde_skrg,skor1,skor2,spin1,spin2,status,_ = room
    if status != 'playing':
        await update.message.reply_text("❌ Room belum siap!", parse_mode='Markdown', reply_to_message_id=update.message.message_id)
        return
    uname = user.username or user.first_name
    if user.id == p1_id:
        if spin1 != -1:
            await update.message.reply_text("⏳ Sudah spin! Tunggu lawan.", parse_mode='Markdown', reply_to_message_id=update.message.message_id)
            return
        angka = spin_roulette()
        update_room(room_id, spin1=angka)
        spin1 = angka
    elif user.id == p2_id:
        if spin2 != -1:
            await update.message.reply_text("⏳ Sudah spin! Tunggu lawan.", parse_mode='Markdown', reply_to_message_id=update.message.message_id)
            return
        angka = spin_roulette()
        update_room(room_id, spin2=angka)
        spin2 = angka
    else:
        return
    reme = hitung_reme(angka)
    await update.message.reply_text(f"@{uname} _*Spun the wheel and got {angka}🎰*_ REME ({reme})", parse_mode='Markdown', reply_to_message_id=update.message.message_id)
    room = get_room(room_id)
    spin1,spin2 = room[8],room[9]
    if spin1 != -1 and spin2 != -1:
        reme1,reme2 = hitung_reme(spin1),hitung_reme(spin2)
        p1u,p2u = get_username(p1_id),get_username(p2_id)
        msg = f"🎮 *Ronde {ronde_skrg}* (Room `{room_id}`)\n@{p1u}: {spin1} → {reme1}\n@{p2u}: {spin2} → {reme2}\n\n"
        if reme1 > reme2:
            skor1 += 1
            msg += f"🏆 Menang: @{p1u}\n"
        elif reme2 > reme1:
            skor2 += 1
            msg += f"🏆 Menang: @{p2u}\n"
        else:
            msg += "🤝 Seri! Tidak ada poin.\n"
        msg += f"📊 Skor: {skor1} - {skor2}"
        if ronde_skrg >= total_ronde:
            total_pot = taruhan * 2
            tax = int(total_pot * TAX_PERCENT / 100)
            hadiah = total_pot - tax
            msg += f"\n\n🎉 *Match Selesai!*\n"
            if skor1 > skor2:
                update_saldo(p1_id, hadiah, 'menang', f'Menang Reme {room_id}')
                saldo_baru = get_saldo(p1_id)
                msg += f"Menang: @{p1u}\n💰 Hadiah: Rp{hadiah:,} (Tax {TAX_PERCENT}% = Rp{tax:,})\nSaldo: {saldo_baru:,}"
            elif skor2 > skor1:
                update_saldo(p2_id, hadiah, 'menang', f'Menang Reme {room_id}')
                saldo_baru = get_saldo(p2_id)
                msg += f"Menang: @{p2u}\n💰 Hadiah: Rp{hadiah:,} (Tax {TAX_PERCENT}% = Rp{tax:,})\nSaldo: {saldo_baru:,}"
            else:
                update_saldo(p1_id, taruhan, 'kembali', 'Seri')
                update_saldo(p2_id, taruhan, 'kembali', 'Seri')
                msg += "🤝 Match Seri! Taruhan dikembalikan."
            delete_room(room_id)
        else:
            update_room(room_id, ronde_sekarang=ronde_skrg+1, skor1=skor1, skor2=skor2, spin1=-1, spin2=-1)
            msg += "\n\nKedua pemain ketik *.spinr* untuk ronde berikutnya."
        await update.message.reply_text(msg, parse_mode='Markdown', reply_to_message_id=update.message.message_id)

async def handle_saldo(update, context):
    user = update.effective_user
    get_user(user.id, user.username or user.first_name)
    saldo = get_saldo(user.id)
    role = get_role(user.id)
    await update.message.reply_text(
        f"💰 *Info Saldo*\n\n• Nama: @{user.username or user.first_name}\n• Role: {role.upper()}\n• Saldo: *Rp{saldo:,}*",
        parse_mode='Markdown', reply_to_message_id=update.message.message_id)

async def handle_topup(update, context):
    user = update.effective_user
    get_user(user.id, user.username or user.first_name)
    parts = update.message.text.strip().split()
    if len(parts) < 2:
        await update.message.reply_text(
            "💳 *Cara Top Up:*\n\n1. Transfer ke DANA owner\n2. Ketik `.topup [jumlah]`\n3. Kirim bukti ke admin\n\nContoh: `.topup 50000`\nMinimal: Rp5.000",
            parse_mode='Markdown', reply_to_message_id=update.message.message_id)
        return
    try:
        jumlah = int(parts[1])
    except:
        await update.message.reply_text("❌ Format salah! Contoh: `.topup 50000`", parse_mode='Markdown', reply_to_message_id=update.message.message_id)
        return
    if jumlah < 5000:
        await update.message.reply_text("❌ Minimum top up Rp5.000!", parse_mode='Markdown', reply_to_message_id=update.message.message_id)
        return
    conn = sqlite3.connect('reme_bot.db')
    c = conn.cursor()
    c.execute('INSERT INTO topup (user_id, jumlah) VALUES (?, ?)', (user.id, jumlah))
    topup_id = c.lastrowid
    conn.commit()
    conn.close()
    uname = user.username or user.first_name
    await update.message.reply_text(
        f"✅ *Request Top Up Diterima!*\n\n• ID: `#{topup_id}`\n• Nama: @{uname}\n• Jumlah: Rp{jumlah:,}\n\n📤 Kirim bukti transfer ke admin!\nSaldo masuk setelah dikonfirmasi.",
        parse_mode='Markdown', reply_to_message_id=update.message.message_id)
    for admin_id in set(OWNER_IDS + ADMIN_IDS):
        try:
            await context.bot.send_message(admin_id,
                f"📥 *Top Up Baru!*\n\n• ID: `#{topup_id}`\n• User: @{uname} (`{user.id}`)\n• Jumlah: Rp{jumlah:,}\n\n✅ Konfirmasi: `.ok {topup_id}`\n❌ Tolak: `.tolak {topup_id}`",
                parse_mode='Markdown', reply_to_message_id=update.message.message_id)
        except:
            pass

async def handle_addsaldo(update, context):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("❌ Akses ditolak!", parse_mode='Markdown', reply_to_message_id=update.message.message_id)
        return
    parts = update.message.text.strip().split()
    is_reply = update.message.reply_to_message and update.message.reply_to_message.from_user
    # Jika reply: .addsaldo [jumlah] | Jika manual: .addsaldo [user_id] [jumlah]
    jumlah_index = 1 if is_reply else 2
    if len(parts) <= jumlah_index:
        await update.message.reply_text(
            "Format:\n• Reply pesan user: `.addsaldo [jumlah]`\n• Manual: `.addsaldo [user_id] [jumlah]`",
            parse_mode='Markdown', reply_to_message_id=update.message.message_id)
        return
    target_id, err = get_target_from_reply_or_args(update, parts, arg_index=1)
    if err:
        await update.message.reply_text(err, parse_mode='Markdown', reply_to_message_id=update.message.message_id)
        return
    if target_id is None:
        await update.message.reply_text("Format: `.addsaldo [user_id] [jumlah]` atau reply pesan user.", parse_mode='Markdown', reply_to_message_id=update.message.message_id)
        return
    try:
        jumlah = int(parts[jumlah_index])
    except:
        await update.message.reply_text("❌ Format jumlah salah!", parse_mode='Markdown', reply_to_message_id=update.message.message_id)
        return
    get_user(target_id)
    update_saldo(target_id, jumlah, 'topup', f'Ditambah admin {user.id}')
    saldo_baru = get_saldo(target_id)
    uname = get_username(target_id)
    await update.message.reply_text(f"✅ *Saldo Ditambah!*\n• User: @{uname} (`{target_id}`)\n• +Rp{jumlah:,}\n• Saldo baru: Rp{saldo_baru:,}", parse_mode='Markdown', reply_to_message_id=update.message.message_id)
    try:
        await context.bot.send_message(target_id, f"✅ *Saldo Ditambah!*\n• +Rp{jumlah:,}\n• Saldo sekarang: Rp{saldo_baru:,}", parse_mode='Markdown', reply_to_message_id=update.message.message_id)
    except:
        pass

async def handle_kurangsaldo(update, context):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("❌ Akses ditolak!", parse_mode='Markdown', reply_to_message_id=update.message.message_id)
        return
    parts = update.message.text.strip().split()
    is_reply = update.message.reply_to_message and update.message.reply_to_message.from_user
    jumlah_index = 1 if is_reply else 2
    if len(parts) <= jumlah_index:
        await update.message.reply_text(
            "Format:\n• Reply pesan user: `.kurangsaldo [jumlah]`\n• Manual: `.kurangsaldo [user_id] [jumlah]`",
            parse_mode='Markdown', reply_to_message_id=update.message.message_id)
        return
    target_id, err = get_target_from_reply_or_args(update, parts, arg_index=1)
    if err:
        await update.message.reply_text(err, parse_mode='Markdown', reply_to_message_id=update.message.message_id)
        return
    if target_id is None:
        await update.message.reply_text("Format: `.kurangsaldo [user_id] [jumlah]` atau reply pesan user.", parse_mode='Markdown', reply_to_message_id=update.message.message_id)
        return
    try:
        jumlah = int(parts[jumlah_index])
    except:
        await update.message.reply_text("❌ Format jumlah salah!", parse_mode='Markdown', reply_to_message_id=update.message.message_id)
        return
    saldo_skrg = get_saldo(target_id)
    if saldo_skrg < jumlah:
        await update.message.reply_text(f"❌ Saldo user tidak cukup! Saldo: Rp{saldo_skrg:,}", parse_mode='Markdown', reply_to_message_id=update.message.message_id)
        return
    get_user(target_id)
    update_saldo(target_id, -jumlah, 'kurang', f'Dikurangi admin {user.id}')
    saldo_baru = get_saldo(target_id)
    uname = get_username(target_id)
    await update.message.reply_text(f"✅ *Saldo Dikurangi!*\n• User: @{uname} (`{target_id}`)\n• -Rp{jumlah:,}\n• Saldo baru: Rp{saldo_baru:,}", parse_mode='Markdown', reply_to_message_id=update.message.message_id)
    try:
        await context.bot.send_message(target_id, f"⚠️ *Saldo Dikurangi!*\n• -Rp{jumlah:,}\n• Saldo sekarang: Rp{saldo_baru:,}", parse_mode='Markdown', reply_to_message_id=update.message.message_id)
    except:
        pass

async def handle_setsaldo(update, context):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("❌ Akses ditolak!", parse_mode='Markdown', reply_to_message_id=upd
