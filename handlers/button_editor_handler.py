import telebot
import logging
import json
from io import BytesIO

logger = logging.getLogger(__name__)

class ButtonEditorHandler:
    def __init__(self, bot, db, language, config):
        self.bot = bot
        self.db = db
        self.language = language
        self.config = config
    
    def handle_export_buttons(self, call):
        """Show button category selection menu"""
        user_id = call.from_user.id
        
        # Verify admin
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            self.bot.answer_callback_query(call.id, "❌ Admin only!")
            return
        
        try:
            # Show category selection
            markup = telebot.types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                telebot.types.InlineKeyboardButton(text="🏠 Main Menu Buttons", callback_data="button_edit_main"),
                telebot.types.InlineKeyboardButton(text="⚙️ Admin Panel Buttons", callback_data="button_edit_admin"),
                telebot.types.InlineKeyboardButton(text="🔘 Navigation Buttons", callback_data="button_edit_nav"),
                telebot.types.InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_panel")
            )
            
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="✏️ <b>Button Editor</b>\n\n"
                     "Select which buttons you want to edit:\n\n"
                     "• <b>Main Menu</b> - Shopping, Cart, Top Up, etc.\n"
                     "• <b>Admin Panel</b> - Store Settings, Products, etc.\n"
                     "• <b>Navigation</b> - Main Menu, Admin Panel buttons",
                reply_markup=markup,
                parse_mode='HTML'
            )
            
            self.bot.answer_callback_query(call.id)
            
        except Exception as e:
            logger.error(f"Error showing button editor: {e}")
            self.bot.answer_callback_query(call.id, "❌ Error")
    
    def handle_button_category(self, call):
        """Handle button category selection"""
        user_id = call.from_user.id
        
        # Verify admin
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            self.bot.answer_callback_query(call.id, "❌ Admin only!")
            return
        
        category = call.data.replace('button_edit_', '')
        
        try:
            # Generate formatted text for this category
            formatted_text = self._generate_category_text(category)
            
            # Send the formatted text
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=formatted_text,
                parse_mode='HTML'
            )
            
            # Follow up message with instructions
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text="👆 <b>Copy the text above, edit the button names, and send it back to me.</b>\n\n"
                     "✏️ Only change the text after the colon (:)\n"
                     "🚫 Don't change button IDs or language codes\n"
                     "💡 You can use emojis!\n\n"
                     "When ready, just send the edited text as a message.",
                parse_mode='HTML'
            )
            
            # Set user state
            self.db.set_user_state(user_id, f'editing_buttons_{category}', {})
            
            self.bot.answer_callback_query(call.id)
            
        except Exception as e:
            logger.error(f"Error generating category text: {e}")
            self.bot.answer_callback_query(call.id, "❌ Error")
    
    def _generate_category_text(self, category):
        """Generate formatted text for a button category"""
        lang_data = self.language.languages
        text = []
        
        if category == 'main':
            text.append("🏠 <b>MAIN MENU BUTTONS</b>\n")
            
            # Get all main menu button IDs from English
            if 'button_texts_mainmenu' in lang_data.get('en', {}):
                for button in lang_data['en']['button_texts_mainmenu']:
                    button_id = button['id']
                    text.append(f"\n📌 <b>{button_id.upper()}</b>")
                    
                    # Show all languages for this button
                    for lang_code, lang_name in [('en', '🇬🇧 EN'), ('ro', '🇷🇴 RO'), ('es', '🇪🇸 ES')]:
                        if lang_code in lang_data and 'button_texts_mainmenu' in lang_data[lang_code]:
                            for btn in lang_data[lang_code]['button_texts_mainmenu']:
                                if btn['id'] == button_id:
                                    text.append(f"{lang_name}: {btn['text']}")
                                    break
        
        elif category == 'admin':
            text.append("⚙️ <b>ADMIN PANEL BUTTONS</b>\n")
            
            if 'button_texts_admin' in lang_data.get('en', {}):
                for button in lang_data['en']['button_texts_admin']:
                    button_id = button['id']
                    text.append(f"\n📌 <b>{button_id.upper()}</b>")
                    
                    for lang_code, lang_name in [('en', '🇬🇧 EN'), ('ro', '🇷🇴 RO'), ('es', '🇪🇸 ES')]:
                        if lang_code in lang_data and 'button_texts_admin' in lang_data[lang_code]:
                            for btn in lang_data[lang_code]['button_texts_admin']:
                                if btn['id'] == button_id:
                                    text.append(f"{lang_name}: {btn['text']}")
                                    break
        
        elif category == 'nav':
            text.append("🔘 <b>NAVIGATION BUTTONS</b>\n")
            
            nav_buttons = ['button_show', 'menu_button_main', 'menu_button_admin']
            nav_names = {
                'button_show': 'Language Selection',
                'menu_button_main': 'Main Menu',
                'menu_button_admin': 'Admin Panel'
            }
            
            for button_id in nav_buttons:
                text.append(f"\n📌 <b>{nav_names[button_id].upper()}</b>")
                
                for lang_code, lang_name in [('en', '🇬🇧 EN'), ('ro', '🇷🇴 RO'), ('es', '🇪🇸 ES')]:
                    if lang_code in lang_data and button_id in lang_data[lang_code]:
                        text.append(f"{lang_name}: {lang_data[lang_code][button_id]}")
        
        return '\n'.join(text)
    
    def _generate_button_file(self):
        """Generate text file content with all button names"""
        content = []
        content.append("# ============================================")
        content.append("# BUTTON NAMES EDITOR")
        content.append("# ============================================")
        content.append("# Edit only the text AFTER the = sign")
        content.append("# DO NOT change button IDs (before =)")
        content.append("# ============================================\n")
        
        # Load current language data
        lang_data = self.language.languages
        
        # Process each language
        for lang_code in ['en', 'ro', 'es']:
            if lang_code not in lang_data:
                continue
            
            lang_name = {'en': 'ENGLISH', 'ro': 'ROMANIAN', 'es': 'SPANISH'}[lang_code]
            content.append(f"\n{'='*50}")
            content.append(f"[{lang_name}]")
            content.append(f"{'='*50}\n")
            
            # Main menu buttons
            if 'button_texts_mainmenu' in lang_data[lang_code]:
                content.append("# Main Menu Buttons:")
                for button in lang_data[lang_code]['button_texts_mainmenu']:
                    content.append(f"{button['id']} = {button['text']}")
                content.append("")
            
            # Admin buttons
            if 'button_texts_admin' in lang_data[lang_code]:
                content.append("# Admin Panel Buttons:")
                for button in lang_data[lang_code]['button_texts_admin']:
                    content.append(f"{button['id']} = {button['text']}")
                content.append("")
            
            # Start button
            if 'button_show' in lang_data[lang_code]:
                content.append("# Language Selection Button:")
                content.append(f"button_show = {lang_data[lang_code]['button_show']}")
                content.append("")
            
            # Menu buttons
            if 'menu_button_main' in lang_data[lang_code]:
                content.append("# Navigation Buttons:")
                content.append(f"menu_button_main = {lang_data[lang_code]['menu_button_main']}")
            if 'menu_button_admin' in lang_data[lang_code]:
                content.append(f"menu_button_admin = {lang_data[lang_code]['menu_button_admin']}")
                content.append("")
        
        content.append("\n# ============================================")
        content.append("# Save this file and send it back to update!")
        content.append("# ============================================")
        
        return '\n'.join(content)
    
    def handle_button_text_input(self, message):
        """Process edited button text from user"""
        user_id = message.from_user.id
        
        # Verify admin
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            return False
        
        # Check if user is in editing state
        user_state = self.db.get_user_state(user_id)
        if not user_state or not user_state['state'].startswith('editing_buttons_'):
            return False
        
        try:
            # Get text content
            text_content = message.text
            if not text_content:
                return False
            
            category = user_state['state'].replace('editing_buttons_', '')
            logger.info(f"Processing button text edit from user {user_id}, category: {category}")
            
            # Parse text and update language data
            success, msg, changes_summary = self._parse_and_update_text(text_content, category)
            
            logger.info(f"Parse result - Success: {success}, Changes summary length: {len(changes_summary)}")
            
            if success:
                # Clear state
                self.db.clear_user_state(user_id)
                
                # Force reload language cache immediately
                self._force_reload_language()
                
                # Build success message with changes summary
                summary_text = "✅ <b>Button names updated successfully!</b>\n\n"
                summary_text += "📝 <b>Changes made:</b>"
                summary_text += changes_summary
                summary_text += "\n\n🔄 Changes applied instantly to all languages.\n"
                summary_text += "✨ All users will see the new button names immediately!"
                
                # Send success message
                self.bot.send_message(
                    message.chat.id,
                    summary_text,
                    parse_mode='HTML'
                )
            else:
                self.bot.send_message(
                    message.chat.id,
                    f"❌ <b>Error updating buttons:</b>\n\n{msg}\n\n"
                    "Please check the file format and try again.",
                    parse_mode='HTML'
                )
            
            return True
            
        except Exception as e:
            logger.error(f"Error processing button file: {e}")
            self.bot.send_message(message.chat.id, f"❌ Error processing file: {str(e)}")
            return True
    
    def _parse_and_update_text(self, text_content, category):
        """Parse edited text and update buttons"""
        try:
            # Load current language.json
            with open('language.json', 'r', encoding='utf-8') as f:
                lang_data = json.load(f)
            
            # Track changes
            changes = []
            lang_names = {'en': '🇬🇧 EN', 'ro': '🇷🇴 RO', 'es': '🇪🇸 ES'}
            
            # Parse the text content
            current_button_id = None
            updates = {}
            
            for line in text_content.split('\n'):
                line = line.strip()
                
                # Check for button ID header (📌 BUTTON_ID)
                if line.startswith('📌'):
                    # Extract button ID
                    current_button_id = line.replace('📌', '').replace('<b>', '').replace('</b>', '').strip().lower()
                    if current_button_id not in updates:
                        updates[current_button_id] = {}
                
                # Check for language line (🇬🇧 EN: Text)
                elif ':' in line and current_button_id:
                    # Parse lang code and text
                    parts = line.split(':', 1)
                    if len(parts) == 2:
                        lang_part = parts[0].strip()
                        new_text = parts[1].strip()
                        
                        # Extract language code
                        lang_code = None
                        if 'EN' in lang_part or '🇬🇧' in lang_part:
                            lang_code = 'en'
                        elif 'RO' in lang_part or '🇷🇴' in lang_part:
                            lang_code = 'ro'
                        elif 'ES' in lang_part or '🇪🇸' in lang_part:
                            lang_code = 'es'
                        
                        if lang_code:
                            updates[current_button_id][lang_code] = new_text
            
            # Apply updates based on category
            if category == 'main':
                for lang_code in ['en', 'ro', 'es']:
                    if lang_code not in lang_data or 'button_texts_mainmenu' not in lang_data[lang_code]:
                        continue
                    
                    for button in lang_data[lang_code]['button_texts_mainmenu']:
                        button_id = button['id']
                        if button_id in updates and lang_code in updates[button_id]:
                            old_text = button['text']
                            new_text = updates[button_id][lang_code]
                            if old_text != new_text:
                                changes.append(f"\n{lang_names[lang_code]}: {button_id} → {old_text} ➜ {new_text}")
                                button['text'] = new_text
            
            elif category == 'admin':
                for lang_code in ['en', 'ro', 'es']:
                    if lang_code not in lang_data or 'button_texts_admin' not in lang_data[lang_code]:
                        continue
                    
                    for button in lang_data[lang_code]['button_texts_admin']:
                        button_id = button['id']
                        if button_id in updates and lang_code in updates[button_id]:
                            old_text = button['text']
                            new_text = updates[button_id][lang_code]
                            if old_text != new_text:
                                changes.append(f"\n{lang_names[lang_code]}: {button_id} → {old_text} ➜ {new_text}")
                                button['text'] = new_text
            
            elif category == 'nav':
                nav_map = {
                    'language selection': 'button_show',
                    'main menu': 'menu_button_main',
                    'admin panel': 'menu_button_admin'
                }
                
                for button_name, button_id in nav_map.items():
                    if button_name in updates:
                        for lang_code in ['en', 'ro', 'es']:
                            if lang_code in updates[button_name] and lang_code in lang_data:
                                old_text = lang_data[lang_code].get(button_id, '')
                                new_text = updates[button_name][lang_code]
                                if old_text != new_text:
                                    changes.append(f"\n{lang_names[lang_code]}: {button_id} → {old_text} ➜ {new_text}")
                                    lang_data[lang_code][button_id] = new_text
            
            # Save updated language.json
            with open('language.json', 'w', encoding='utf-8') as f:
                json.dump(lang_data, f, ensure_ascii=False, indent=4)
            
            # Build summary
            if changes:
                changes_summary = "".join(changes)
            else:
                changes_summary = "\n  ℹ️ <i>No changes detected - all button names are the same as before.</i>"
            
            # Reload language data in memory
            self.language.reload_languages()
            
            return True, "Success", changes_summary
            
        except Exception as e:
            logger.error(f"Error parsing button text: {e}")
            return False, str(e), ""
    
    def _parse_and_update_buttons(self, file_content):
        """Parse uploaded file and update language.json"""
        try:
            # Parse file
            lang_updates = {'en': {}, 'ro': {}, 'es': {}}
            current_lang = None
            
            for line in file_content.split('\n'):
                line = line.strip()
                
                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue
                
                # Check for language section
                if line == '[ENGLISH]':
                    current_lang = 'en'
                    continue
                elif line == '[ROMANIAN]':
                    current_lang = 'ro'
                    continue
                elif line == '[SPANISH]':
                    current_lang = 'es'
                    continue
                elif line.startswith('==='):
                    continue
                
                # Parse button definition
                if '=' in line and current_lang:
                    parts = line.split('=', 1)
                    if len(parts) == 2:
                        button_id = parts[0].strip()
                        button_text = parts[1].strip()
                        lang_updates[current_lang][button_id] = button_text
            
            # Load current language.json
            with open('language.json', 'r', encoding='utf-8') as f:
                lang_data = json.load(f)
            
            # Track changes
            changes = []
            lang_names = {'en': '🇬🇧 EN', 'ro': '🇷🇴 RO', 'es': '🇪🇸 ES'}
            
            # Update button texts and track changes
            for lang_code, updates in lang_updates.items():
                if lang_code not in lang_data:
                    continue
                
                lang_changes = []
                
                # Update main menu buttons
                if 'button_texts_mainmenu' in lang_data[lang_code]:
                    for button in lang_data[lang_code]['button_texts_mainmenu']:
                        if button['id'] in updates:
                            old_text = button['text']
                            new_text = updates[button['id']]
                            if old_text != new_text:
                                lang_changes.append(f"  • {button['id']}: {old_text} → {new_text}")
                            button['text'] = new_text
                
                # Update admin buttons
                if 'button_texts_admin' in lang_data[lang_code]:
                    for button in lang_data[lang_code]['button_texts_admin']:
                        if button['id'] in updates:
                            old_text = button['text']
                            new_text = updates[button['id']]
                            if old_text != new_text:
                                lang_changes.append(f"  • {button['id']}: {old_text} → {new_text}")
                            button['text'] = new_text
                
                # Update other buttons
                if 'button_show' in updates:
                    old_text = lang_data[lang_code].get('button_show', '')
                    new_text = updates['button_show']
                    if old_text != new_text:
                        lang_changes.append(f"  • button_show: {old_text} → {new_text}")
                    lang_data[lang_code]['button_show'] = new_text
                    
                if 'menu_button_main' in updates:
                    old_text = lang_data[lang_code].get('menu_button_main', '')
                    new_text = updates['menu_button_main']
                    if old_text != new_text:
                        lang_changes.append(f"  • menu_button_main: {old_text} → {new_text}")
                    lang_data[lang_code]['menu_button_main'] = new_text
                    
                if 'menu_button_admin' in updates:
                    old_text = lang_data[lang_code].get('menu_button_admin', '')
                    new_text = updates['menu_button_admin']
                    if old_text != new_text:
                        lang_changes.append(f"  • menu_button_admin: {old_text} → {new_text}")
                    lang_data[lang_code]['menu_button_admin'] = new_text
                
                if lang_changes:
                    changes.append(f"\n{lang_names[lang_code]}:\n" + "\n".join(lang_changes))
            
            # Save updated language.json
            with open('language.json', 'w', encoding='utf-8') as f:
                json.dump(lang_data, f, ensure_ascii=False, indent=4)
            
            # Build summary
            if changes:
                changes_summary = "".join(changes)
            else:
                changes_summary = "\n  ℹ️ <i>No changes detected - all button names are the same as before.</i>"
            
            # Reload language data in memory
            self.language.load_languages()
            
            return True, "Success", changes_summary
            
        except Exception as e:
            logger.error(f"Error parsing button file: {e}")
            return False, str(e), ""
    
    def _force_reload_language(self):
        """Force reload language data and clear all caches"""
        try:
            # Reload language data in memory for ALL handlers (they share the same Language instance)
            self.language.reload_languages()
            
            logger.info("✅ Language cache cleared and reloaded successfully for ALL handlers")
        except Exception as e:
            logger.error(f"Error force reloading language: {e}")
    
    def handle_cancel_edit(self, call):
        """Cancel button editing"""
        user_id = call.from_user.id
        self.db.clear_user_state(user_id)
        self.bot.answer_callback_query(call.id, "✅ Cancelled")
        
        # Return to admin panel
        from handlers.admin_handler import AdminHandler
        admin_handler = AdminHandler(self.bot, self.db, self.language, self.config)
        admin_handler.handle_admin_panel(call)
