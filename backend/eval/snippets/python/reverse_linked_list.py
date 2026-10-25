class ListNode:
    def __init__(self, val, next=None):
        self.val = val
        self.next = next


def reverse(head):
    prev = None
    cur = head
    while cur:
        nxt = cur.next
        cur.next = prev
        prev = cur
        cur = nxt
    return prev


head = ListNode(1, ListNode(2, ListNode(3)))
head = reverse(head)
