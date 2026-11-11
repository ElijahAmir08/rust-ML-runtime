use std::collections::VecDeque;
#[derive(Debug)]
pub struct Request {
    pub id: u64,
}
pub struct RequestQueue{
    //Implementing queue with a double-ended queue (VecDequeue) for FIFO (Enter through the tail and leave the front)
    pending_requests: VecDeque<Request>,
}

impl RequestQueue {
    // Creates a new RequestQueue
    pub fn new() -> Self {
        Self {
            pending_requests: VecDeque::new(),
        }
    }
    // Adds a request to the queue (back of the queue)
    // Borrows mutable reference to self so that the queue can be modified, and moves request into the queue 
    pub fn enqueue(&mut self, request: Request) {
        self.pending_requests.push_back(request);
    }
    // Removes the oldest request 
    // Returns None if the queue is empty (via the Option type)
    pub fn dequeue(&mut self) -> Option<Request> {
        self.pending_requests.pop_front()
    }
    // Returns the number of requests in the queue
    pub fn len(&mut self) -> usize {
        self.pending_requests.len()
    }
}

// Add a test module to test the RequestQueue implementation
#[cfg(test)] //Compile this module when running tests
mod tests { //Creates module containing the tests
    use super::*; //Import items from the parent module

    #[test]
    fn test_fifo_order() {
        let mut queue = RequestQueue::new();

        queue.enqueue(Request { id: 1 });
        queue.enqueue(Request { id: 2 });
        queue.enqueue(Request { id: 3 });

        assert_eq!(queue.len(), 3);
        
        //Since dequeue returns an option type, the unwrap function will extract its value if some or panic for none
        assert_eq!(queue.dequeue().unwrap().id, 1);
        assert_eq!(queue.dequeue().unwrap().id, 2);
        assert_eq!(queue.dequeue().unwrap().id, 3);

         assert_eq!(queue.len(), 0);
    }
    #[test]
    fn test_empty_queue() {
        let mut queue = RequestQueue::new();

        assert!(queue.dequeue().is_none());
    }
}