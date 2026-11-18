
/* 
This file may be used via PyO3 to replace request_queue.py in vLLM.

*/
use std::collections::VecDeque;
#[derive(Debug)]
pub struct Request {
    pub id: u64,
    pub arrival_ms: u64,
    pub duration_ms: u64,
}
// Structure to represent the process results of a request
#[derive(Debug)]
pub struct ScheduleRecord {
    pub id: u64,
    pub start_ms: u64,
    pub finish_ms: u64,
    pub wait_ms: u64,
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
    //enqueue is the equivalent as add_request()
    pub fn enqueue(&mut self, request: Request) {
        self.pending_requests.push_back(request);
    }
    // Removes the oldest request 
    // Returns None if the queue is empty (via the Option type)
    //enqueue is the equivalent as pop_request()
    pub fn dequeue(&mut self) -> Option<Request> {
        self.pending_requests.pop_front()
    }
    // Returns the number of requests in the queue
    pub fn len(&self) -> usize {
        self.pending_requests.len()
    }
}

//simulate_fifo function to return a collection of request's processing results
pub fn simulate_fifo(queue: &mut RequestQueue) -> Vec<ScheduleRecord> {

    let mut now_ms = 0;
    let mut records = Vec::new();
    // While dequeuing returns a request calculate times
    while let Some(request) = queue.dequeue() {
        let start_ms = now_ms.max(request.arrival_ms);
        let finish_ms = start_ms + request.duration_ms;
        let wait_ms = start_ms - request.arrival_ms;
        //Record the results
        records.push(ScheduleRecord {
            id: request.id,
            start_ms,
            finish_ms,
            wait_ms,
        });
        now_ms = finish_ms;
    }
    records
}

// Add a test module to test the RequestQueue implementation
#[cfg(test)] //Compile this module when running tests
mod tests { //Creates module containing the tests
    use super::*; //Import items from the parent module

    #[test]
    fn test_fifo_order() {
        let mut queue = RequestQueue::new();

        queue.enqueue(Request { id: 1, arrival_ms: 0, duration_ms: 50});
        queue.enqueue(Request { id: 2, arrival_ms: 3, duration_ms: 60 });
        queue.enqueue(Request { id: 3, arrival_ms: 5, duration_ms: 66 });

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
    // Chat GPT 6.1 helped create the two tests below, for the sake of time I had it create any remaining important tests
    
    #[test]
    // Checks that the same queue can be reused and preserves the correct requests
    // Stresses filling, emptying, and reusing the same queue
    fn test_fields_and_repeated_operations() {
        let mut queue = RequestQueue::new();
        for cycle in 0..100 {
            queue.enqueue(Request { id: cycle, arrival_ms: 100, duration_ms: 0 });
            queue.enqueue(Request { id: cycle, arrival_ms: 0, duration_ms: 25 });
            let first = queue.dequeue().unwrap();
            assert_eq!((first.id, first.arrival_ms, first.duration_ms), (cycle, 100, 0));
            assert_eq!(queue.len(), 1);
            let second = queue.dequeue().unwrap();
            assert_eq!((second.id, second.arrival_ms, second.duration_ms), (cycle, 0, 25));
            assert!(queue.dequeue().is_none());
        }
    }

    #[test]
    //Checks the timing calculations from simulate_fifo
    fn test_simulate_fifo_waiting_and_idle_time() {
        let mut queue = RequestQueue::new();
        queue.enqueue(Request { id: 1, arrival_ms: 5, duration_ms: 10 });
        queue.enqueue(Request { id: 2, arrival_ms: 8, duration_ms: 3 });
        queue.enqueue(Request { id: 3, arrival_ms: 30, duration_ms: 0 });

        let records = simulate_fifo(&mut queue);
        let actual: Vec<_> = records.iter()
            .map(|record| (record.id, record.start_ms, record.finish_ms, record.wait_ms))
            .collect();
        assert_eq!(actual, vec![(1, 5, 15, 0), (2, 15, 18, 7), (3, 30, 30, 0)]);
        assert_eq!(queue.len(), 0);
        assert!(simulate_fifo(&mut queue).is_empty());
    }
}