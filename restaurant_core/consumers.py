import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

class OrderConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.role = self.scope['url_route']['kwargs'].get('role')
        self.user_id = self.scope['url_route']['kwargs'].get('user_id')
        self.groups = []

        # 1. Role Based Group Assignment
        if self.role == 'customer':
            table_no = await self.get_table_from_session(self.user_id)
            if table_no:
                self.groups.append(f'table_{table_no}')
            else:
                print(f"❌ Connection Rejected: No session for {self.user_id}")
                await self.close()
                return
        
        else:
            # Staff Roles
            if self.role == 'waiter':
                self.groups.append('waiters_group')
            elif self.role == 'chef':
                self.groups.append('kitchen_group')
            elif self.role == 'barman':
                self.groups.append('bar_group')
            elif self.role in ['admin', 'superuser']:
                self.groups.extend(['kitchen_group', 'bar_group', 'waiters_group'])
                self.groups.append('admin_group')

        # 2. Channel Layer mein Groups register karein
        for group in self.groups:
            await self.channel_layer.group_add(group, self.channel_name)
        
        # 3. Connection Accept karein
        await self.accept()

        # 🌟 4. INITIAL MESSAGE (Ye Flutter ko "LIVE" status switch karne mein madad karta hai)
        await self.send(text_data=json.dumps({
            "notification_type": "CONNECTION_ESTABLISHED",
            "message": f"Successfully connected as {self.role}",
            "groups": self.groups
        }))

        print(f"✅ WS Connected: {self.role} (ID: {self.user_id}) -> Groups: {self.groups}")

    async def disconnect(self, close_code):
        for group in self.groups:
            await self.channel_layer.group_discard(group, self.channel_name)
        print(f"❌ WS Disconnected: {self.role}")

    # Master Router (utils.py) se notifications receive karne ke liye
    async def order_notification(self, event):
        await self.send(text_data=json.dumps(event['payload']))

    # Database access for customer sessions
    @database_sync_to_async
    def get_table_from_session(self, session_id):
        from restaurant_core.models import GuestSession # Ensure path is correct
        try:
            return GuestSession.objects.get(id=session_id).table_number
        except Exception as e:
            print(f"DB Error in WS: {e}")
            return None